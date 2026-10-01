"""Polite, SSRF-safe HTTP fetcher used for every page SignalLens reads.

:meth:`Fetcher.fetch` never raises for network or HTTP problems; it returns a
:class:`FetchResult` whose ``error`` (network / timeout / decode problems) or ``blocked``
(``"robots"``, ``"ssrf"``, ``"too_large"``, ``"unsupported_scheme"``) field explains what
went wrong. For every request it:

1. checks the URL against the SSRF policy - and again for every redirect hop, because
   redirects are followed manually (``follow_redirects=False``);
2. checks robots.txt (unless disabled) and honours ``Crawl-delay`` (capped at 10 s);
3. spaces consecutive requests to the same host by at least ``min_host_interval_s``;
4. sends ``If-None-Match`` / ``If-Modified-Since`` when given (304 -> ``not_modified``);
5. streams the body and stops at ``max_bytes`` (decompressed size, so gzip bombs stop too);
6. decodes text-like bodies: header charset, else ``<meta charset>`` sniffed from the first
   4 KB, else UTF-8 with replacement characters.

``sandbox://<slug>`` URLs are served by an injected resolver without any network access
(the demo sandbox).
"""

from __future__ import annotations

import asyncio
import codecs
import html as html_lib
import logging
import re
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

import httpx

from signallens.fetch.robots import RobotsPolicy
from signallens.fetch.ssrf import SSRFBlocked, assert_public_url

__all__ = ["FetchResult", "Fetcher", "SandboxResolver"]

logger = logging.getLogger(__name__)

SandboxResolver = Callable[[str], Awaitable[tuple[str, str] | None]]

_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
_ACCEPT = "text/html,application/xhtml+xml,application/pdf;q=0.9,*/*;q=0.8"
_MAX_CRAWL_DELAY_S = 10.0
_TEXT_TYPES = frozenset(
    {
        "application/xhtml+xml",
        "application/xml",
        "application/json",
        "application/ld+json",
        "application/rss+xml",
        "application/atom+xml",
        "application/javascript",
    }
)
_META_CHARSET = re.compile(rb"""<meta[^>]+charset\s*=\s*["']?\s*([A-Za-z0-9_.:-]+)""", re.IGNORECASE)
_XML_ENCODING = re.compile(rb"""<\?xml[^>]+encoding\s*=\s*["']([A-Za-z0-9_.:-]+)["']""", re.IGNORECASE)
# WHATWG: documents labelled latin-1 are decoded as windows-1252 by every browser.
_ENCODING_ALIASES = {"iso-8859-1": "cp1252", "latin-1": "cp1252", "latin1": "cp1252", "us-ascii": "cp1252"}


@dataclass
class FetchResult:
    url: str
    final_url: str
    status: int | None
    content_type: str | None
    content: bytes
    text: str | None  # decoded for text-like types (html/xml/json/text), else None
    etag: str | None
    last_modified: str | None
    not_modified: bool
    elapsed_ms: int
    error: str | None = None  # network/timeout/decode problem
    blocked: str | None = None  # "robots" | "ssrf" | "too_large" | "unsupported_scheme"
    from_sandbox: bool = False

    @property
    def ok(self) -> bool:
        return (
            self.status is not None
            and 200 <= self.status < 300
            and self.error is None
            and self.blocked is None
        )

    @property
    def media_type(self) -> str:
        """Lowercased content type without parameters (``""`` when unknown)."""
        return (self.content_type or "").split(";", 1)[0].strip().lower()


def _is_textual(media_type: str, body: bytes) -> bool:
    if media_type.startswith("text/") or media_type in _TEXT_TYPES:
        return True
    if media_type.endswith(("+xml", "+json")):
        return True
    if not media_type:  # unlabelled: text unless it looks binary
        head = body[:1024]
        return not head.startswith(b"%PDF") and b"\x00" not in head
    return False


def _charset_from_header(content_type: str | None) -> str | None:
    if not content_type:
        return None
    for param in content_type.split(";")[1:]:
        name, _, value = param.partition("=")
        if name.strip().lower() == "charset" and value.strip():
            return value.strip().strip("\"'")
    return None


def _lookup_codec(label: str | None) -> str | None:
    if not label:
        return None
    label = label.strip().lower()
    label = _ENCODING_ALIASES.get(label, label)
    try:
        return codecs.lookup(label).name
    except LookupError:
        return None


def decode_body(body: bytes, content_type: str | None) -> str | None:
    """Decode a response body to text, or ``None`` for binary content types."""
    media_type = (content_type or "").split(";", 1)[0].strip().lower()
    if not _is_textual(media_type, body):
        return None
    for bom, codec in (
        (codecs.BOM_UTF8, "utf-8"),
        (codecs.BOM_UTF16_LE, "utf-16-le"),
        (codecs.BOM_UTF16_BE, "utf-16-be"),
    ):
        if body.startswith(bom):
            return body[len(bom) :].decode(codec, errors="replace")
    codec = _lookup_codec(_charset_from_header(content_type))
    if codec is None and media_type not in {"application/json", "application/ld+json"}:
        head = body[:4096]
        match = _META_CHARSET.search(head) or _XML_ENCODING.search(head)
        if match:
            sniffed = _lookup_codec(match.group(1).decode("ascii", errors="ignore"))
            # A <meta> we could read as ASCII cannot really be UTF-16/32 (HTML spec rule).
            if sniffed is not None and not sniffed.startswith(("utf-16", "utf-32")):
                codec = sniffed
    return body.decode(codec or "utf-8", errors="replace")


@dataclass
class _Response:
    status: int
    headers: httpx.Headers
    body: bytes
    too_large: bool


class Fetcher:
    """HTTP(S) fetcher with SSRF protection, robots.txt, politeness and size limits."""

    def __init__(
        self,
        *,
        user_agent: str,
        timeout_s: float = 20.0,
        max_bytes: int = 8_000_000,
        respect_robots: bool = True,
        allow_private_hosts: bool = False,
        min_host_interval_s: float = 1.0,
        max_redirects: int = 5,
        sandbox_resolver: SandboxResolver | None = None,
        http: httpx.AsyncClient | None = None,
    ) -> None:
        self.user_agent = user_agent
        self.timeout_s = timeout_s
        self.max_bytes = max_bytes
        self.respect_robots = respect_robots
        self.allow_private_hosts = allow_private_hosts
        self.min_host_interval_s = min_host_interval_s
        self.max_redirects = max_redirects
        self._sandbox_resolver = sandbox_resolver
        self._owns_http = http is None
        self._http = http if http is not None else httpx.AsyncClient(timeout=httpx.Timeout(timeout_s))
        self.robots = RobotsPolicy(self._fetch_robots_txt, user_agent)
        self._host_locks: dict[str, asyncio.Lock] = {}
        self._host_last: dict[str, float] = {}

    async def aclose(self) -> None:
        if self._owns_http:
            await self._http.aclose()

    async def __aenter__(self) -> Fetcher:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()

    # ------------------------------------------------------------------ public API

    async def fetch(
        self,
        url: str,
        *,
        etag: str | None = None,
        last_modified: str | None = None,
        check_robots: bool = True,
    ) -> FetchResult:
        """Fetch ``url``. Never raises for network/HTTP problems (see :class:`FetchResult`)."""
        started = time.perf_counter()
        try:
            if url.strip().lower().startswith("sandbox://"):
                return await self._fetch_sandbox(url, started)
            return await self._fetch_http(
                url, etag=etag, last_modified=last_modified, check_robots=check_robots and self.respect_robots
            )
        except Exception as exc:  # last-resort guard: a fetch must never crash the pipeline
            logger.exception("unexpected error fetching %s", url)
            return _failure(url, url, started, error=f"unexpected error: {type(exc).__name__}: {exc}")

    # ------------------------------------------------------------------ internals

    async def _fetch_sandbox(self, url: str, started: float) -> FetchResult:
        slug = url.strip()[len("sandbox://") :].strip("/")
        if self._sandbox_resolver is None:
            return _failure(url, url, started, blocked="unsupported_scheme")
        try:
            resolved = await self._sandbox_resolver(slug)
        except Exception as exc:
            logger.warning("sandbox resolver failed for %r: %s", slug, exc)
            return _failure(url, url, started, error=f"sandbox resolver failed: {exc}")
        if resolved is None:
            return FetchResult(
                url=url,
                final_url=url,
                status=404,
                content_type="text/html; charset=utf-8",
                content=b"",
                text="",
                etag=None,
                last_modified=None,
                not_modified=False,
                elapsed_ms=_ms(started),
                from_sandbox=True,
            )
        html, title = resolved
        if title and not re.search(r"<title[\s>]", html, re.IGNORECASE):
            html = (
                f"<!doctype html><html><head><title>{html_lib.escape(title)}</title></head>"
                f"<body>{html}</body></html>"
            )
        return FetchResult(
            url=url,
            final_url=url,
            status=200,
            content_type="text/html; charset=utf-8",
            content=html.encode("utf-8"),
            text=html,
            etag=None,
            last_modified=None,
            not_modified=False,
            elapsed_ms=_ms(started),
            from_sandbox=True,
        )

    async def _fetch_http(
        self, url: str, *, etag: str | None, last_modified: str | None, check_robots: bool
    ) -> FetchResult:
        headers = {"User-Agent": self.user_agent, "Accept": _ACCEPT, "Accept-Language": "en"}
        if etag:
            headers["If-None-Match"] = etag
        if last_modified:
            headers["If-Modified-Since"] = last_modified

        current = url.strip()
        network_s = 0.0
        for _hop in range(self.max_redirects + 1):
            try:
                parts = urlsplit(current)
                _ = parts.port  # raises ValueError for an out-of-range or non-numeric port
            except ValueError as exc:
                return _failure(url, current, None, error=f"invalid URL: {exc}", network_s=network_s)
            if parts.scheme.lower() not in ("http", "https"):
                return _failure(url, current, None, blocked="unsupported_scheme", network_s=network_s)
            try:
                await assert_public_url(current, allow_private=self.allow_private_hosts)
            except SSRFBlocked as exc:
                logger.warning("blocked by SSRF policy: %s (%s)", current, exc)
                return _failure(url, current, None, blocked="ssrf", network_s=network_s)
            except OSError as exc:
                return _failure(
                    url, current, None, error=f"dns resolution failed: {exc}", network_s=network_s
                )

            crawl_delay = None
            if check_robots:
                if not await self.robots.allowed(current):
                    logger.info("disallowed by robots.txt: %s", current)
                    return _failure(url, current, None, blocked="robots", network_s=network_s)
                crawl_delay = await self.robots.crawl_delay(current)

            host = (parts.hostname or "").lower()
            interval = max(self.min_host_interval_s, min(crawl_delay or 0.0, _MAX_CRAWL_DELAY_S))
            t0 = time.perf_counter()
            try:
                response = await self._polite_get(host, interval, current, headers)
            except (TimeoutError, httpx.TimeoutException):
                return _failure(
                    url, current, None, error=f"timeout after {self.timeout_s:g}s", network_s=network_s
                )
            except httpx.DecodingError as exc:
                return _failure(url, current, None, error=f"decode error: {exc}", network_s=network_s)
            except (httpx.InvalidURL, httpx.UnsupportedProtocol) as exc:
                return _failure(url, current, None, error=f"invalid URL: {exc}", network_s=network_s)
            except httpx.HTTPError as exc:
                return _failure(url, current, None, error=f"{type(exc).__name__}: {exc}", network_s=network_s)
            network_s += time.perf_counter() - t0

            location = response.headers.get("location")
            if response.status in _REDIRECT_STATUSES and location:
                current = urljoin(current, location.strip())
                continue
            return self._result(url, current, response, etag, last_modified, network_s)

        return _failure(
            url, current, None, error=f"too many redirects (>{self.max_redirects})", network_s=network_s
        )

    def _result(
        self,
        url: str,
        final_url: str,
        response: _Response,
        sent_etag: str | None,
        sent_last_modified: str | None,
        network_s: float,
    ) -> FetchResult:
        content_type = response.headers.get("content-type")
        result = FetchResult(
            url=url,
            final_url=final_url,
            status=response.status,
            content_type=content_type,
            content=b"",
            text=None,
            etag=response.headers.get("etag"),
            last_modified=response.headers.get("last-modified"),
            not_modified=False,
            elapsed_ms=int(network_s * 1000),
        )
        if response.status == 304:
            result.not_modified = True
            result.etag = result.etag or sent_etag
            result.last_modified = result.last_modified or sent_last_modified
            return result
        if response.too_large:
            result.blocked = "too_large"
            return result
        result.content = response.body
        try:
            result.text = decode_body(response.body, content_type)
        except Exception as exc:  # decoding with "replace" should not fail; be safe anyway
            result.error = f"decode error: {exc}"
        return result

    async def _polite_get(self, host: str, interval: float, url: str, headers: dict[str, str]) -> _Response:
        lock = self._host_locks.setdefault(host, asyncio.Lock())
        async with lock:  # one request at a time per host, spaced by `interval`
            last = self._host_last.get(host)
            if last is not None:
                wait = last + interval - time.monotonic()
                if wait > 0:
                    await asyncio.sleep(wait)
            try:
                async with asyncio.timeout(self.timeout_s):
                    return await self._get(url, headers)
            finally:
                self._host_last[host] = time.monotonic()
                self._prune_hosts()

    async def _get(self, url: str, headers: dict[str, str]) -> _Response:
        async with self._http.stream(
            "GET", url, headers=headers, follow_redirects=False, timeout=httpx.Timeout(self.timeout_s)
        ) as response:
            status = response.status_code
            if status in _REDIRECT_STATUSES or status == 304:
                return _Response(status, response.headers, b"", False)
            declared = response.headers.get("content-length")
            if declared and declared.strip().isdigit() and int(declared) > self.max_bytes:
                return _Response(status, response.headers, b"", True)
            chunks: list[bytes] = []
            size = 0
            async for chunk in response.aiter_bytes():
                size += len(chunk)
                if size > self.max_bytes:
                    return _Response(status, response.headers, b"", True)
                chunks.append(chunk)
            return _Response(status, response.headers, b"".join(chunks), False)

    def _prune_hosts(self) -> None:
        """Forget idle hosts so a long-running worker does not accumulate one lock per host."""
        if len(self._host_last) <= 1000:
            return
        horizon = time.monotonic() - max(60.0, self.min_host_interval_s, _MAX_CRAWL_DELAY_S)
        for host, last in list(self._host_last.items()):
            lock = self._host_locks.get(host)
            if last < horizon and (lock is None or not lock.locked()):
                self._host_last.pop(host, None)
                self._host_locks.pop(host, None)

    async def _fetch_robots_txt(self, robots_url: str) -> tuple[int | None, str | None]:
        """Fetch callable for :class:`RobotsPolicy`: status + text, ``(None, None)`` on failure."""
        result = await self._fetch_http(robots_url, etag=None, last_modified=None, check_robots=False)
        if result.error or result.blocked in ("ssrf", "unsupported_scheme"):
            return None, None
        return result.status, result.text


def _ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


def _failure(
    url: str,
    final_url: str,
    started: float | None,
    *,
    error: str | None = None,
    blocked: str | None = None,
    network_s: float = 0.0,
) -> FetchResult:
    elapsed = _ms(started) if started is not None else int(network_s * 1000)
    return FetchResult(
        url=url,
        final_url=final_url,
        status=None,
        content_type=None,
        content=b"",
        text=None,
        etag=None,
        last_modified=None,
        not_modified=False,
        elapsed_ms=elapsed,
        error=error,
        blocked=blocked,
    )
