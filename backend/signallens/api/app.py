"""FastAPI application factory. All routes live under ``/api``."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from signallens import __version__
from signallens.api.routes import (
    agent,
    approvals,
    ask,
    auth,
    members,
    monitoring,
    plans,
    reports,
    runs,
    sandbox,
    sso,
    system,
    workspaces,
    world,
)
from signallens.config import Settings, get_settings
from signallens.db.session import make_engine, make_session_factory
from signallens.runtime.services import Services, build_services

log = logging.getLogger(__name__)

AGENT_PREFIX = "/api/agent"
_AGENT_CORS = [
    (b"access-control-allow-origin", b"*"),
    (b"access-control-allow-methods", b"GET, POST, OPTIONS"),
    (b"access-control-allow-headers", b"Content-Type, X-API-Key, Authorization"),
    (b"access-control-max-age", b"86400"),
]


class PublicAgentCORS:
    """Open CORS (no cookies) for /api/agent/*, which authenticates by API key, not session."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http" or not scope["path"].startswith(AGENT_PREFIX):
            await self.app(scope, receive, send)
            return
        if scope["method"] == "OPTIONS":
            await send({"type": "http.response.start", "status": 204, "headers": _AGENT_CORS})
            await send({"type": "http.response.body", "body": b""})
            return

        async def send_with_cors(message) -> None:
            if message["type"] == "http.response.start":
                headers = [h for h in message.get("headers", []) if not h[0].lower().startswith(b"access-control-")]
                message = {**message, "headers": headers + _AGENT_CORS}
            await send(message)

        await self.app(scope, receive, send_with_cors)


def create_app(settings: Settings | None = None, services: Services | None = None) -> FastAPI:
    settings = settings or get_settings()
    if settings.env == "prod" and (settings.secret_key.startswith("dev-insecure") or len(settings.secret_key) < 32):
        raise RuntimeError("Set SL_SECRET_KEY to a random value of at least 32 characters in production.")

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = None
        svc = services
        if svc is None:
            engine = make_engine(settings.database_url)
            svc = build_services(settings, make_session_factory(engine))
        app.state.services = svc
        worker_task = worker = None
        if settings.run_worker_in_api:
            from signallens.jobs.worker import Worker

            worker = Worker(svc)
            worker_task = asyncio.create_task(worker.run())
            log.info("in-process worker started")
        try:
            yield
        finally:
            if worker is not None:
                worker.stop()
                await asyncio.gather(worker_task, return_exceptions=True)
            if services is None:
                await svc.aclose()
                if engine is not None:
                    await engine.dispose()

    app = FastAPI(title="SignalLens API", version=__version__, lifespan=lifespan)
    if services is not None:
        app.state.services = services  # tests drive the app without running lifespan
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=True,
                       allow_methods=["*"], allow_headers=["*"])
    # Added last = outermost: the public agent endpoints answer cross-origin calls from any site
    # (marketplaces and testers call them from the browser); everything else keeps the strict policy.
    app.add_middleware(PublicAgentCORS)

    @app.get("/", include_in_schema=False)
    async def index() -> dict[str, object]:
        base = settings.public_api_url.rstrip("/")
        return {
            "name": "SignalLens API",
            "agent": {
                "brief": f"POST {base}/api/agent/brief  {{\"company\": \"Razorpay\", \"your_company\": \"...\"}}",
                "brief_get": f"GET {base}/api/agent/brief?company=Razorpay",
                "async": f"POST {base}/api/agent/briefs, then GET {base}/api/agent/briefs/{{brief_id}}",
                "health": f"{base}/api/agent/health",
                "manifest": f"{base}/api/agent/manifest",
            },
            "docs": f"{base}/docs",
            "web_app": settings.public_app_url,
        }
    api = APIRouter(prefix="/api")
    for module in (system, auth, workspaces, plans, reports, world, monitoring, runs, approvals, sandbox, ask):
        api.include_router(module.router)
    for module in (sso, members):  # single sign-on; workspace members and roles
        api.include_router(module.router)
    api.include_router(agent.router)  # hosted one-shot brief agent (aiKart method 2)
    app.include_router(api)
    return app


app = create_app()
