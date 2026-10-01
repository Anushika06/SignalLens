"""Entry points around :func:`run_brief`: local tools, remote delegation and the aiKart contract.

**aiKart "Try Me Now" contract** (docs/hackathon/aikart-agent-manifest-guide.pdf): inputs
arrive as JSON in ``/aikart/input.json`` (also ``$AIKART_INPUT``); the container must write
``{"format": "markdown", "response": "..."}`` to ``/aikart/output.json`` and exit 0. A
non-zero exit shows the buyer a generic error, so every problem we can explain (missing
keys, bad input, provider outage) becomes a friendly markdown response instead. Only a
failure to write the output file itself is a non-zero exit.

**Where the brief runs.** With model + search keys in the environment it runs inside the
container. A public image cannot carry secret keys, so the published image is built with
``SL_REMOTE_AGENT_URL`` pointing at the hosted SignalLens API; the container then calls
``POST {url}/api/agent/brief`` (the domain must be in the manifest's egress allowlist).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from signallens.brief.agent import run_brief
from signallens.brief.models import BriefInput, BriefRequestError, BriefResult, parse_brief_request
from signallens.brief.reader import make_reader, reader_mode
from signallens.config import Settings, get_settings

log = logging.getLogger(__name__)

AIKART_DIR = Path("/aikart")
HARD_CAP_S = 275.0  # aiKart kills the container at 280 s


@dataclass
class LocalTools:
    llm: Any
    search: Any
    fetcher: Any
    wayback: Any

    async def aclose(self) -> None:
        for closer in (self.fetcher.aclose, self.wayback.aclose, getattr(self.search, "aclose", None),
                       getattr(getattr(self.llm, "provider", None), "aclose", None)):
            if closer is None:
                continue
            try:
                await closer()
            except Exception:  # pragma: no cover - best effort
                log.debug("close failed", exc_info=True)


def build_local_tools(settings: Settings) -> LocalTools | None:
    """Model + search + fetcher + archive client without a database; None if keys are missing."""
    from signallens.fetch.http import Fetcher
    from signallens.fetch.wayback import WaybackClient
    from signallens.runtime.services import build_gateway, build_search

    llm = build_gateway(settings)
    search = build_search(settings)
    if llm is None or search is None:
        return None
    fetcher = Fetcher(user_agent=settings.user_agent, timeout_s=min(settings.fetch_timeout_s, 20.0),
                      max_bytes=settings.fetch_max_bytes, respect_robots=settings.respect_robots,
                      min_host_interval_s=0.5)
    return LocalTools(llm=llm, search=search, fetcher=fetcher, wayback=WaybackClient(fetcher))


def tavily_for(search: Any, settings: Settings) -> Any:
    """The Tavily client used for page extraction (the search provider itself when it is Tavily)."""
    if hasattr(search, "extract"):
        return search
    if settings.tavily_api_key:
        from signallens.search.tavily import TavilySearch

        return TavilySearch(settings.tavily_api_key)
    return None


async def run_local(inputs: BriefInput, settings: Settings, tools: LocalTools, *, on_step=None) -> BriefResult:
    reader = make_reader(reader_mode(), fetcher=tools.fetcher, tavily=tavily_for(tools.search, settings))
    return await run_brief(inputs, llm=tools.llm, search=tools.search, reader=reader, wayback=tools.wayback,
                           deadline_s=settings.brief_timeout_s, on_step=on_step, app_url=settings.public_app_url)


class RemoteError(RuntimeError):
    pass


async def run_remote(inputs: BriefInput, settings: Settings, *, timeout_s: float = 268.0) -> str:
    """Delegate to a hosted SignalLens: ``POST {url}/api/agent/brief``; returns its markdown."""
    url = (settings.remote_agent_url or "").rstrip("/") + "/api/agent/brief"
    headers = {"Content-Type": "application/json"}
    if settings.remote_agent_key:
        headers["X-API-Key"] = settings.remote_agent_key
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(timeout_s, connect=15.0)) as http:
            resp = await http.post(url, json=inputs.model_dump(), headers=headers)
    except httpx.HTTPError as e:
        raise RemoteError(f"could not reach the hosted SignalLens agent ({type(e).__name__})") from e
    try:
        body = resp.json()
    except ValueError:
        body = {}
    if resp.status_code != 200 or not isinstance(body, dict) or not body.get("response"):
        detail = body.get("detail") if isinstance(body, dict) else None
        raise RemoteError(f"the hosted SignalLens agent answered HTTP {resp.status_code}"
                          + (f": {str(detail)[:300]}" if detail else ""))
    return str(body["response"])


def error_markdown(title: str, message: str, *, hint: str | None = None, settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    parts = [f"# SignalLens — {title}", "", message]
    if hint:
        parts += ["", hint]
    parts += ["", "---", "_For continuous monitoring, approvals and team routing use the SignalLens web app at "
              f"{settings.public_app_url}_"]
    return "\n".join(parts) + "\n"


NOT_CONFIGURED_HINT = (
    "**How to configure:** run the container with model and search keys "
    "(`-e NVIDIA_API_KEY=... -e TAVILY_API_KEY=...`), or build it with "
    "`--build-arg SL_REMOTE_AGENT_URL=https://<your-signallens-api>` so it delegates to a hosted SignalLens "
    "(that domain must be in the manifest's `egressAllowlist`)."
)


async def produce_markdown(raw_input: Any, settings: Settings | None = None) -> str:
    """Turn raw aiKart input into the response markdown. Never raises."""
    settings = settings or get_settings()
    try:
        inputs = parse_brief_request(raw_input)
    except BriefRequestError as e:
        return error_markdown("input needed", str(e), settings=settings)
    tools = build_local_tools(settings)
    if tools is not None:
        try:
            result = await asyncio.wait_for(run_local(inputs, settings, tools), HARD_CAP_S - 5)
            return result.markdown
        except TimeoutError:
            return error_markdown("time limit", f"The brief on {inputs.company} did not finish within the sandbox "
                                  "time limit. Please try again with a narrower focus.", settings=settings)
        except Exception as e:  # any provider/runtime failure becomes a readable answer
            log.exception("local brief failed")
            return error_markdown("could not complete the brief",
                                  f"The agent hit an error while researching {inputs.company}: "
                                  f"{type(e).__name__}. Please try again in a minute.", settings=settings)
        finally:
            await tools.aclose()
    if settings.remote_agent_url:
        try:
            return await run_remote(inputs, settings, timeout_s=HARD_CAP_S - 7)
        except RemoteError as e:
            return error_markdown("hosted agent unavailable", f"This container delegates to the hosted SignalLens "
                                  f"agent, but {e}. Please try again shortly.", settings=settings)
    return error_markdown(
        "not configured",
        "This SignalLens container has no model/search API keys and no hosted agent URL, so it cannot research "
        f"{inputs.company}.", hint=NOT_CONFIGURED_HINT, settings=settings,
    )


def _read_json_file(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as e:
        return {"__error__": f"could not parse {path.name}: {type(e).__name__}"}


def aikart_paths() -> tuple[Any, Path]:
    """(raw input, output path) per the aiKart contract, with a local-testing fallback.

    Input: ``/aikart/input.json``, else ``$AIKART_INPUT``, else ``$AIKART_DIR/input.json``.
    Output: ``$AIKART_DIR/output.json`` when ``AIKART_DIR`` is set, else ``/aikart/output.json``.
    """
    local = Path(os.environ["AIKART_DIR"]) if os.environ.get("AIKART_DIR") else None
    raw: Any = None
    if (AIKART_DIR / "input.json").is_file():
        raw = _read_json_file(AIKART_DIR / "input.json")
    elif os.environ.get("AIKART_INPUT", "").strip():
        try:
            raw = json.loads(os.environ["AIKART_INPUT"])
        except ValueError:
            raw = os.environ["AIKART_INPUT"]  # a bare string is treated as the company
    elif local is not None and (local / "input.json").is_file():
        raw = _read_json_file(local / "input.json")
    return raw, (local or AIKART_DIR) / "output.json"


def write_output(path: Path, markdown: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps({"format": "markdown", "response": markdown}, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def aikart_main() -> int:
    """``signallens aikart-run``: 0 whenever output.json was written, 1 otherwise."""
    raw, out_path = aikart_paths()
    settings = get_settings()
    if raw is None:
        markdown = error_markdown("input needed", "No input was provided (expected /aikart/input.json or "
                                  "$AIKART_INPUT), e.g. {\"company\": \"Razorpay\"}.", settings=settings)
    elif isinstance(raw, dict) and "__error__" in raw:
        markdown = error_markdown("input needed", f"The input file is not valid JSON ({raw['__error__']}).",
                                  settings=settings)
    else:
        try:
            markdown = asyncio.run(produce_markdown(raw, settings))
        except Exception as e:  # pragma: no cover - produce_markdown already never raises
            markdown = error_markdown("unexpected error", f"{type(e).__name__}", settings=settings)
    try:
        write_output(out_path, markdown)
    except OSError as e:
        log.error("could not write %s: %s", out_path, e)
        return 1
    print(f"wrote {out_path} ({len(markdown)} characters)")
    return 0
