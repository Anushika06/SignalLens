"""Opt-in JavaScript rendering with a headless Chromium (Playwright).

Some official pages arrive as an empty *JavaScript shell*: a ``<div id="root">`` plus
script bundles, with the real text rendered in the browser. The quality gate rejects those
as "too little text". When ``SL_RENDER_JS=true`` and Playwright is installed
(``uv sync --extra browser`` + ``uv run playwright install chromium``), such a page is
rendered here, re-extracted, and monitored like any other page.

Only JavaScript shells are rendered. Anti-bot challenges and CAPTCHAs are **never**
rendered or bypassed: :func:`js_shell_reason` refuses any page with challenge markers.

Security - the browser runs untrusted JavaScript, so every request it makes is checked:

* every request (document, subresource, XHR/fetch, worker) goes through a route handler
  that applies the same SSRF policy as the fetcher (:func:`assert_public_url`): private,
  loopback, link-local, CGNAT and metadata addresses are refused;
* redirects are followed *by the handler*, hop by hop, each hop checked (Chromium does not
  route redirect hops itself);
* service workers are blocked (they would bypass routing), WebSockets are refused, and
  downloads, popups and JavaScript dialogs are cancelled/dismissed;
* images, media and fonts are aborted (speed; the text is all we need);
* one browser per process, launched lazily, at most :data:`MAX_CONCURRENT_RENDERS`
  pages at once; :func:`close_renderer` shuts it down.

The residual DNS-rebinding risk is the same as the fetcher's (see ``fetch.ssrf``).
"""

from __future__ import annotations

import asyncio
import dataclasses
import logging
import os
import re
import sys
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlsplit

from signallens.fetch.extract import ExtractedDoc, detect_challenge, extract_result
from signallens.fetch.http import FetchResult
from signallens.fetch.ssrf import SSRFBlocked, assert_public_url

__all__ = [
    "RENDERED_NOTE",
    "RenderBlocked",
    "RenderError",
    "RenderOutcome",
    "RenderResult",
    "RenderUnavailable",
    "close_renderer",
    "js_shell_reason",
    "render_availability",
    "render_if_js_shell",
    "render_page",
]

log = logging.getLogger(__name__)

MAX_CONCURRENT_RENDERS = 2
RENDERED_NOTE = "rendered with headless browser"
DISABLED_REASON = "needs JavaScript rendering (disabled on this deployment)"
_BLOCKED_RESOURCE_TYPES = frozenset({"image", "media", "font", "ping", "manifest", "texttrack"})
_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
_MAX_REDIRECTS = 5
_MIN_RENDERED_WORDS = 30
_SHELL_MAX_WORDS = 30

UrlPolicy = Callable[[str], Awaitable[bool]]
Renderer = Callable[..., Awaitable["RenderResult"]]


class RenderError(RuntimeError):
    """Rendering failed (navigation error, timeout, ...)."""


class RenderUnavailable(RenderError):
    """Playwright or its Chromium build is not installed, or cannot start here."""


class RenderBlocked(RenderError):
    """The page (or where it redirected to) is not allowed by the SSRF policy."""


@dataclass
class RenderResult:
    html: str
    final_url: str
    status: int | None
    blocked_requests: int = 0


# --------------------------------------------------------------------------- JS-shell detection

_MOUNT_POINT = re.compile(
    r"""<(?:div|main|body)[^>]+id\s*=\s*["'](?:root|app|__next|__nuxt|___gatsby|svelte|q-app|react-root|"""
    r"""app-root|main-app|application)["']|<app-root[\s>]|\bng-version=|\bdata-reactroot\b|\bdata-server-rendered\b|"""
    r"""window\.__NUXT__|__NEXT_DATA__|data-sveltekit""",
    re.IGNORECASE,
)
_NOSCRIPT_JS = re.compile(r"<noscript[^>]*>[^<]{0,400}(?:javascript|enable js)", re.IGNORECASE)
_SCRIPT_TAG = re.compile(r"<script\b", re.IGNORECASE)
# Never render anything that looks like a bot wall, even if it is also script-heavy.
_CHALLENGE_HINTS = ("captcha", "challenge-platform", "cf-chl", "cf_chl", "are you a robot", "verify you are human",
                    "datadome", "perimeterx", "px-captcha", "_incapsula", "incapsula", "ddos-guard",
                    "checking your browser", "bot detection", "access denied", "request unsuccessful")


def js_shell_reason(fetch: FetchResult, doc: ExtractedDoc) -> str | None:
    """Why this fetched page looks like an empty JavaScript shell, or ``None``.

    Only HTML pages that came back fine (2xx), extracted to almost no text, carry script
    bundles plus a client-side mount point (or a "please enable JavaScript" ``<noscript>``)
    qualify. Anything that looks like an anti-bot challenge is excluded, by design.
    """
    if fetch.from_sandbox or not fetch.ok or doc.quality == "blocked" or doc.challenge:
        return None
    if doc.kind not in ("html", "unknown") or not fetch.text:
        return None
    if doc.word_count >= _SHELL_MAX_WORDS:
        return None
    raw = fetch.text[:400_000]
    lowered = raw.casefold()
    if detect_challenge(raw, doc.title, doc.word_count) or any(h in lowered for h in _CHALLENGE_HINTS):
        return None
    scripts = len(_SCRIPT_TAG.findall(raw))
    if scripts == 0:
        return None
    signals = []
    if _MOUNT_POINT.search(raw):
        signals.append("client-side app mount point")
    if _NOSCRIPT_JS.search(raw):
        signals.append("asks to enable JavaScript")
    if not signals and scripts >= 3 and len(raw) > 3_000:
        signals.append(f"{scripts} scripts and almost no text")
    if not signals:
        return None
    return f"empty JavaScript shell ({', '.join(signals)}; {doc.word_count} words without JavaScript)"


# --------------------------------------------------------------------------- availability


def _browsers_dir() -> Path | None:
    env = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
    if env == "0":
        return None  # browsers inside the package; can't cheaply tell
    if env:
        return Path(env)
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "ms-playwright"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Caches" / "ms-playwright"
    return Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "ms-playwright"


def render_availability() -> tuple[bool, str]:
    """(available, detail) - a cheap check without launching a browser."""
    try:
        import playwright.async_api  # noqa: F401
    except ImportError:
        return False, "Playwright is not installed (uv sync --extra browser)"
    folder = _browsers_dir()
    if folder is not None and not any(folder.glob("chromium*")):
        return False, "Chromium is not installed (uv run playwright install chromium)"
    try:
        from importlib.metadata import version

        return True, f"Playwright {version('playwright')}"
    except Exception:  # pragma: no cover
        return True, "Playwright"


# --------------------------------------------------------------------------- browser lifecycle


class _BrowserPool:
    """One Chromium per process (per event loop), launched on first use."""

    def __init__(self) -> None:
        self.loop = asyncio.get_running_loop()
        self.lock = asyncio.Lock()
        self.semaphore = asyncio.Semaphore(MAX_CONCURRENT_RENDERS)
        self.playwright: Any = None
        self.browser: Any = None

    async def get(self) -> Any:
        async with self.lock:
            if self.browser is not None and self.browser.is_connected():
                return self.browser
            try:
                from playwright.async_api import async_playwright
            except ImportError as e:
                raise RenderUnavailable("Playwright is not installed (uv sync --extra browser)") from e
            try:
                if self.playwright is None:
                    self.playwright = await async_playwright().start()
                self.browser = await self.playwright.chromium.launch(headless=True, args=[
                    "--disable-dev-shm-usage",
                    "--disable-background-networking",
                    "--disable-extensions",
                    "--disable-sync",
                    "--no-first-run",
                    "--mute-audio",
                    "--force-webrtc-ip-handling-policy=disable_non_proxied_udp",
                    "--webrtc-ip-handling-policy=disable_non_proxied_udp",
                ])
            except NotImplementedError as e:  # e.g. a Windows SelectorEventLoop cannot spawn processes
                raise RenderUnavailable("this event loop cannot start the browser process") from e
            except Exception as e:
                text = str(e)
                if "Executable doesn't exist" in text or "playwright install" in text:
                    raise RenderUnavailable("Chromium is not installed (uv run playwright install chromium)") from e
                raise RenderUnavailable(f"could not launch Chromium: {text.splitlines()[0][:200]}") from e
            return self.browser

    async def close(self) -> None:
        async with self.lock:
            browser, pw = self.browser, self.playwright
            self.browser = self.playwright = None
        for closer in (getattr(browser, "close", None), getattr(pw, "stop", None)):
            if closer is None:
                continue
            try:
                await closer()
            except Exception:  # pragma: no cover - best effort
                log.debug("renderer close failed", exc_info=True)


_pool: _BrowserPool | None = None


def _get_pool() -> _BrowserPool:
    global _pool
    loop = asyncio.get_running_loop()
    if _pool is None or _pool.loop is not loop or loop.is_closed():
        _pool = _BrowserPool()
    return _pool


async def close_renderer() -> None:
    """Close the shared browser (no-op when it was never started)."""
    global _pool
    pool, _pool = _pool, None
    if pool is not None and pool.browser is not None:
        try:
            if pool.loop is asyncio.get_running_loop():
                await pool.close()
        except RuntimeError:  # pragma: no cover - no running loop
            pass


# --------------------------------------------------------------------------- request guard


def ssrf_policy(allow_private: bool = False) -> UrlPolicy:
    """The fetcher's SSRF policy as an async predicate, cached per scheme/host/port."""
    cache: dict[tuple[str, str, int | None], bool] = {}

    async def allowed(url: str) -> bool:
        try:
            parts = urlsplit(url)
            key = (parts.scheme.lower(), (parts.hostname or "").lower(), parts.port)
        except ValueError:
            return False
        if key not in cache:
            try:
                await assert_public_url(url, allow_private=allow_private)
                cache[key] = True
            except (SSRFBlocked, OSError):
                cache[key] = False
        return cache[key]

    return allowed


class _Guard:
    def __init__(self, policy: UrlPolicy, timeout_ms: float) -> None:
        self.policy = policy
        self.timeout_ms = timeout_ms
        self.blocked = 0
        self.blocked_document: str | None = None

    async def _deny(self, route: Any, url: str, why: str) -> None:
        self.blocked += 1
        if route.request.is_navigation_request() and route.request.frame.parent_frame is None:
            self.blocked_document = url
        log.info("render: blocked %s (%s)", url, why)
        await route.abort("blockedbyclient")

    async def handle(self, route: Any) -> None:
        req = route.request
        try:
            if req.resource_type in _BLOCKED_RESOURCE_TYPES:
                await route.abort("blockedbyclient")
                return
            scheme = urlsplit(req.url).scheme.lower()
            if scheme in ("data", "blob"):
                await route.continue_()
                return
            if scheme not in ("http", "https") or not await self.policy(req.url):
                await self._deny(route, req.url, "not a public http(s) address")
                return
            # Follow redirects here, checking every hop: Chromium does not route redirect hops.
            current, method = req.url, None
            resp = await route.fetch(max_redirects=0, timeout=self.timeout_ms)
            hops = 0
            while resp.status in _REDIRECT_STATUSES and resp.headers.get("location"):
                hops += 1
                nxt = urljoin(current, resp.headers["location"].strip())
                if hops > _MAX_REDIRECTS:
                    await self._deny(route, nxt, "too many redirects")
                    return
                if urlsplit(nxt).scheme.lower() not in ("http", "https") or not await self.policy(nxt):
                    await self._deny(route, nxt, "redirect to a non-public address")
                    return
                if resp.status == 303 or (resp.status in (301, 302) and req.method == "POST"):
                    method = "GET"
                await resp.dispose()
                current = nxt
                resp = await route.fetch(url=current, method=method, max_redirects=0, timeout=self.timeout_ms)
            if hops and req.is_navigation_request():
                # Point the browser straight at the vetted final URL so the page gets the right
                # base URL; the chain to it was just checked hop by hop.
                await resp.dispose()
                await route.fulfill(status=302, headers={"location": current}, body="")
                return
            await route.fulfill(response=resp)
        except Exception as e:  # network error, page closed, ...
            log.debug("render: request %s failed: %s", req.url, e)
            try:
                await route.abort("failed")
            except Exception:
                pass


# --------------------------------------------------------------------------- rendering

_WORDS_JS = (
    "(n) => !!document.body && (document.body.innerText || '').trim().split(/\\s+/).filter(Boolean).length >= n"
)


async def render_page(
    url: str,
    *,
    timeout_s: float = 25.0,
    user_agent: str | None = None,
    allow_private: bool = False,
    max_bytes: int = 8_000_000,
    url_policy: UrlPolicy | None = None,
) -> RenderResult:
    """Render ``url`` in headless Chromium and return the resulting DOM as HTML.

    Raises :class:`RenderUnavailable` (no Playwright/Chromium), :class:`RenderBlocked`
    (SSRF policy) or :class:`RenderError` (navigation failure).
    """
    policy = url_policy or ssrf_policy(allow_private)
    if not await policy(url):
        raise RenderBlocked(f"{url} is not a public address")
    pool = _get_pool()
    async with pool.semaphore:
        browser = await pool.get()
        from playwright.async_api import Error as PlaywrightError
        from playwright.async_api import TimeoutError as PlaywrightTimeout

        timeout_ms = timeout_s * 1000
        context = await browser.new_context(
            user_agent=user_agent, accept_downloads=False, service_workers="block", java_script_enabled=True,
            locale="en-US", viewport={"width": 1280, "height": 2000},
        )
        try:
            guard = _Guard(policy, timeout_ms)
            await context.route("**/*", guard.handle)
            if hasattr(context, "route_web_socket"):
                async def _no_websockets(ws: Any) -> None:
                    await ws.close()

                await context.route_web_socket("**/*", _no_websockets)
            page = await context.new_page()
            page.on("dialog", lambda d: asyncio.ensure_future(d.dismiss()))
            page.on("download", lambda d: asyncio.ensure_future(d.cancel()))
            page.on("popup", lambda p: asyncio.ensure_future(p.close()))
            started = time.monotonic()

            def remaining_ms(cap_s: float) -> float:
                return max(500.0, min(cap_s, timeout_s - (time.monotonic() - started)) * 1000)

            try:
                response = await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            except PlaywrightTimeout as e:
                raise RenderError(f"timed out after {timeout_s:g}s loading the page") from e
            except PlaywrightError as e:
                if guard.blocked_document:
                    raise RenderBlocked(f"{guard.blocked_document} is not a public address") from e
                raise RenderError(f"navigation failed: {str(e).splitlines()[0][:200]}") from e
            if guard.blocked_document:
                raise RenderBlocked(f"{guard.blocked_document} is not a public address")
            # Wait for text to appear, then briefly for late requests to settle. Apps that keep a
            # connection open never reach "networkidle", so that wait is short.
            for waiter in (lambda: page.wait_for_function(_WORDS_JS, arg=_MIN_RENDERED_WORDS,
                                                          timeout=remaining_ms(12)),
                           lambda: page.wait_for_load_state("networkidle", timeout=remaining_ms(3))):
                try:
                    await waiter()
                except PlaywrightTimeout:
                    pass
            html = await page.content()
            final_url = page.url
            if not await policy(final_url):
                raise RenderBlocked(f"{final_url} is not a public address")
            if len(html.encode("utf-8", errors="ignore")) > max_bytes:
                html = html.encode("utf-8", errors="ignore")[:max_bytes].decode("utf-8", errors="ignore")
            return RenderResult(html=html, final_url=final_url, status=response.status if response else None,
                                blocked_requests=guard.blocked)
        finally:
            try:
                await context.close()
            except Exception:  # pragma: no cover
                log.debug("context close failed", exc_info=True)


# --------------------------------------------------------------------------- pipeline helper


@dataclass
class RenderOutcome:
    fetch: FetchResult
    doc: ExtractedDoc
    rendered: bool = False
    note: str | None = None  # "rendered with headless browser", or why it was not


async def render_if_js_shell(
    fetch: FetchResult,
    doc: ExtractedDoc,
    *,
    enabled: bool,
    timeout_s: float,
    user_agent: str | None,
    allow_private: bool = False,
    max_bytes: int = 8_000_000,
    renderer: Renderer | None = None,
) -> RenderOutcome:
    """If ``doc`` failed the quality gate because the page is a JavaScript shell, render it.

    Returns the (possibly replaced) fetch result and extracted doc. When rendering is off or
    unavailable, the doc keeps its failing quality with a clear reason. Anti-bot challenges
    are never rendered.
    """
    if doc.quality == "ok":
        return RenderOutcome(fetch, doc)
    shell = js_shell_reason(fetch, doc)
    if shell is None:
        return RenderOutcome(fetch, doc)
    if not enabled:
        doc.quality, doc.quality_reason = "degenerate", DISABLED_REASON
        return RenderOutcome(fetch, doc, note=DISABLED_REASON)
    url = fetch.final_url or fetch.url
    try:
        result = await (renderer or render_page)(url, timeout_s=timeout_s, user_agent=user_agent,
                                                 allow_private=allow_private, max_bytes=max_bytes)
    except RenderUnavailable as e:
        reason = f"needs JavaScript rendering (unavailable on this deployment: {e})"
    except RenderBlocked as e:
        reason = f"needs JavaScript rendering; the browser was not allowed to load it ({e})"
    except Exception as e:
        reason = f"needs JavaScript rendering; the headless browser failed ({type(e).__name__}: {e})"
    else:
        rendered = dataclasses.replace(
            fetch, final_url=result.final_url or fetch.final_url, status=result.status or fetch.status,
            content_type="text/html; charset=utf-8", content=result.html.encode("utf-8", errors="ignore"),
            text=result.html,
            # Validators describe the raw shell, not the rendered data: never reuse them.
            etag=None, last_modified=None,
        )
        new_doc = extract_result(rendered, mode="page")
        if new_doc.quality != "ok":
            reason = f"{RENDERED_NOTE}, but the page is still unusable: {new_doc.quality_reason}"
            new_doc.quality_reason = reason
            return RenderOutcome(fetch, new_doc, rendered=True, note=reason)
        log.info("rendered %s with headless browser (%s)", url, shell)
        return RenderOutcome(rendered, new_doc, rendered=True, note=RENDERED_NOTE)
    log.info("could not render %s: %s", url, reason)
    doc.quality, doc.quality_reason = "degenerate", reason[:500]
    return RenderOutcome(fetch, doc, note=reason[:500])
