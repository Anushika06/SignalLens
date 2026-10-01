"""Hosted agent endpoint (aiKart method 2): one-shot intelligence briefs over HTTP.

Other platforms and agents call SignalLens without a user account, so these routes use an
API key instead of a session: when ``SL_AGENT_API_KEYS`` is set, ``X-API-Key`` (or
``Authorization: Bearer``) must match one of them; when it is empty the endpoint is open.
Either way each client (key, else IP) gets ``SL_AGENT_RATE_LIMIT_PER_HOUR`` brief requests
per rolling hour - a brief costs several minutes of model calls.

Bodies are parsed leniently (see :func:`signallens.brief.models.parse_brief_request`).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import threading
import time
import uuid
from collections import deque
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from signallens import __version__
from signallens.api.deps import services
from signallens.brief.models import (
    AGENT_DESCRIPTION,
    AGENT_DISPLAY_NAME,
    AGENT_NAME,
    INPUT_FIELDS,
    BriefRequestError,
    parse_brief_request,
)
from signallens.brief.reader import reader_mode
from signallens.brief.service import create_brief, run_stored_brief
from signallens.db.models import AgentBrief
from signallens.db.session import transaction
from signallens.jobs.queue import PRIORITY_INTERACTIVE, enqueue
from signallens.runtime.services import Services

router = APIRouter(prefix="/agent", tags=["agent"])

WINDOW_S = 3600.0


class RateLimiter:
    """In-memory sliding-window limiter (per process; good enough for one API instance)."""

    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def hit(self, client: str, limit: int, *, now: float | None = None) -> int | None:
        """Record a request; returns None if allowed, else seconds until the next slot frees."""
        now = time.monotonic() if now is None else now
        with self._lock:
            hits = self._hits.setdefault(client, deque())
            while hits and hits[0] <= now - WINDOW_S:
                hits.popleft()
            if len(hits) >= limit:
                return max(1, int(hits[0] + WINDOW_S - now))
            hits.append(now)
            if len(self._hits) > 10_000:  # forget idle clients
                for key in [k for k, v in self._hits.items() if not v]:
                    del self._hits[key]
            return None


def _limiter(request: Request) -> RateLimiter:
    limiter = getattr(request.app.state, "agent_rate_limiter", None)
    if limiter is None:
        limiter = request.app.state.agent_rate_limiter = RateLimiter()
    return limiter


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded.strip():
        return forwarded.split(",")[0].strip()  # behind a proxy (Render, Fly): the original client
    return request.client.host if request.client else "unknown"


def _supplied_key(request: Request) -> str | None:
    key = request.headers.get("x-api-key")
    if not key:
        auth = request.headers.get("authorization", "")
        if auth.lower().startswith("bearer "):
            key = auth[7:]
    return key.strip() if key and key.strip() else None


def agent_client(request: Request, svc: Services = Depends(services)) -> str:
    """Authenticate the caller (when keys are configured) and return its rate-limit identity."""
    keys = svc.settings.agent_api_key_set
    supplied = _supplied_key(request)
    if keys:
        if not supplied or not any(hmac.compare_digest(supplied.encode(), k.encode()) for k in keys):
            raise HTTPException(status_code=401, detail="Missing or invalid API key (send it as X-API-Key).")
        return "key:" + hashlib.sha256(supplied.encode()).hexdigest()[:16]
    return "ip:" + _client_ip(request)


def rate_limited_client(request: Request, client: str = Depends(agent_client),
                        svc: Services = Depends(services)) -> str:
    wait = _limiter(request).hit(client, max(1, svc.settings.agent_rate_limit_per_hour))
    if wait is not None:
        raise HTTPException(status_code=429, detail=f"Rate limit reached. Try again in {wait} s.",
                            headers={"Retry-After": str(wait)})
    return client


async def _body(request: Request) -> Any:
    raw = await request.body()
    if not raw.strip():
        return {}
    text = raw.decode("utf-8", errors="replace")
    try:
        return json.loads(text)
    except ValueError:
        return text  # plain text body: treat it as the company / question


async def _parsed_inputs(request: Request):
    try:
        return parse_brief_request(await _body(request))
    except BriefRequestError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


def _require_configured(svc: Services) -> None:
    missing = [name for name, ok in (("language model", svc.llm is not None), ("search", svc.search is not None))
               if not ok]
    if missing:
        raise HTTPException(status_code=503, detail=f"The agent is not configured on this server ({' and '.join(missing)} "
                                                    "missing).")


def _out(row: AgentBrief, base: str) -> dict[str, Any]:
    out: dict[str, Any] = {
        "brief_id": str(row.id), "status": row.status, "input": row.input, "created_at": row.created_at.isoformat(),
        "finished_at": row.finished_at.isoformat() if row.finished_at else None,
        "poll_url": f"{base}/api/agent/briefs/{row.id}", "trace": row.trace or [],
    }
    if row.status == "succeeded":
        out.update({"format": "markdown", "response": row.markdown, "data": row.result})
    if row.error:
        out["error"] = row.error
    return out


@router.get("/health")
async def agent_health(svc: Services = Depends(services)) -> dict[str, Any]:
    return {"status": "ok", "llm_configured": svc.llm is not None, "search_configured": svc.search is not None,
            "version": __version__, "reader": reader_mode()}


@router.get("/manifest")
async def agent_manifest(svc: Services = Depends(services)) -> dict[str, Any]:
    base = svc.settings.public_api_url.rstrip("/")
    return {
        "name": AGENT_NAME,
        "display_name": AGENT_DISPLAY_NAME,
        "description": AGENT_DESCRIPTION,
        "version": __version__,
        "inputs": INPUT_FIELDS,
        "output": {"format": "markdown"},
        "auth": {"type": "api_key", "header": "X-API-Key", "required": bool(svc.settings.agent_api_key_set)},
        "rate_limit_per_hour": svc.settings.agent_rate_limit_per_hour,
        "timeout_s": svc.settings.brief_timeout_s,
        "endpoints": {
            "brief": {"method": "POST", "url": f"{base}/api/agent/brief", "mode": "synchronous",
                      "returns": {"format": "markdown", "response": "<markdown>", "brief_id": "...", "data": {},
                                  "trace": []}},
            "submit": {"method": "POST", "url": f"{base}/api/agent/briefs", "mode": "asynchronous",
                       "returns": {"brief_id": "...", "status": "queued", "poll_url": "..."}},
            "poll": {"method": "GET", "url": f"{base}/api/agent/briefs/{{brief_id}}"},
            "health": {"method": "GET", "url": f"{base}/api/agent/health"},
        },
        "example_request": {"company": "Razorpay", "your_company": "Cashfree Payments — payment gateway for Indian "
                            "SMBs", "focus": "Everything", "language": "English", "months_back": 12},
        "web_app": svc.settings.public_app_url,
    }


@router.post("/brief")
async def agent_brief(request: Request, client: str = Depends(rate_limited_client),
                      svc: Services = Depends(services)):
    inputs = await _parsed_inputs(request)
    _require_configured(svc)
    brief_id = await create_brief(svc, inputs, client=client, status="running")
    outcome = await run_stored_brief(svc, brief_id)
    async with svc.session_factory() as s:
        row = await s.get(AgentBrief, brief_id)
    if row is None or row.status != "succeeded":
        return JSONResponse(status_code=500, content={
            "detail": f"The brief could not be completed ({outcome.get('error') or 'unknown error'}).",
            "brief_id": str(brief_id)})
    return {"format": "markdown", "response": row.markdown, "brief_id": str(brief_id), "data": row.result,
            "trace": row.trace}


@router.post("/briefs", status_code=202)
async def agent_submit(request: Request, client: str = Depends(rate_limited_client),
                       svc: Services = Depends(services)) -> dict[str, Any]:
    inputs = await _parsed_inputs(request)
    _require_configured(svc)
    brief_id = await create_brief(svc, inputs, client=client, status="queued")
    async with transaction(svc.session_factory) as s:
        await enqueue(s, "agent_brief", {"brief_id": str(brief_id)}, priority=PRIORITY_INTERACTIVE,
                      dedupe_key=f"agent_brief:{brief_id}", max_attempts=1)
    base = svc.settings.public_api_url.rstrip("/")
    return {"brief_id": str(brief_id), "status": "queued", "poll_url": f"{base}/api/agent/briefs/{brief_id}"}


@router.get("/briefs/{brief_id}")
async def agent_poll(brief_id: uuid.UUID, _client: str = Depends(agent_client),
                     svc: Services = Depends(services)) -> dict[str, Any]:
    async with svc.session_factory() as s:
        row = await s.get(AgentBrief, brief_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Brief not found")
    return _out(row, svc.settings.public_api_url.rstrip("/"))
