"""Internet Archive (Wayback Machine) client for history backfill (C5).

A new customer should not wait weeks for history. During baseline, official pages are
backfilled from the archive: the CDX API lists roughly one capture per month, and each
capture's *original* bytes (the ``id_`` URL form, without the Wayback toolbar) are fetched
through the normal :class:`~signallens.fetch.http.Fetcher` and replayed through the same
extraction and change-detection pipeline.

The archive is a shared public service: requests from this client are spaced by
``min_interval_s`` and CDX calls back off on 429/5xx (2 s, 5 s, 10 s) before giving up with
:class:`WaybackError`. Archived captures of real pages include challenge and error pages -
run every capture through the quality gate before comparing it.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Literal

import httpx

from signallens.fetch.http import Fetcher, FetchResult

__all__ = ["AVAILABILITY_ENDPOINT", "CDX_ENDPOINT", "ArchiveCapture", "WaybackClient", "WaybackError"]

logger = logging.getLogger(__name__)

# Indirection so tests can replace backoff sleeps without touching asyncio globally.
_sleep = asyncio.sleep

CDX_ENDPOINT = "https://web.archive.org/cdx/search/cdx"
AVAILABILITY_ENDPOINT = "https://archive.org/wayback/available"
_RETRY_DELAYS_S = (2.0, 5.0, 10.0)
_COLLAPSE = {"month": "timestamp:6", "day": "timestamp:8"}


@dataclass
class ArchiveCapture:
    timestamp: str  # 14-digit Wayback timestamp, e.g. "20240112184857"
    captured_at: datetime
    original_url: str
    status: int | None
    digest: str | None
    length: int | None

    @property
    def archive_url(self) -> str:
        """Human-facing archive page (with the Wayback toolbar)."""
        return f"https://web.archive.org/web/{self.timestamp}/{self.original_url}"

    @property
    def raw_url(self) -> str:
        """The captured bytes exactly as archived, without toolbar or URL rewriting."""
        return f"https://web.archive.org/web/{self.timestamp}id_/{self.original_url}"


class WaybackError(Exception):
    """The CDX API could not be queried (after retries) or answered nonsense."""


def _int_or_none(value: object) -> int | None:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


def _parse_cdx(payload: object) -> list[ArchiveCapture]:
    """Parse ``output=json`` CDX rows: the first row is the header naming the columns."""
    if not isinstance(payload, list) or len(payload) < 2 or not isinstance(payload[0], list):
        return []
    header = [str(col) for col in payload[0]]
    captures: dict[str, ArchiveCapture] = {}
    for row in payload[1:]:
        if not isinstance(row, list) or len(row) != len(header):
            continue
        fields = dict(zip(header, row, strict=True))
        timestamp = str(fields.get("timestamp") or "")
        original = str(fields.get("original") or "")
        if not timestamp.isdigit() or len(timestamp) < 8 or not original:
            continue
        try:
            captured_at = datetime.strptime(timestamp[:14].ljust(14, "0"), "%Y%m%d%H%M%S").replace(tzinfo=UTC)
        except ValueError:
            continue
        digest = fields.get("digest")
        captures[timestamp] = ArchiveCapture(
            timestamp=timestamp,
            captured_at=captured_at,
            original_url=original,
            status=_int_or_none(fields.get("statuscode")),
            digest=str(digest) if digest not in (None, "", "-") else None,
            length=_int_or_none(fields.get("length")),
        )
    return [captures[ts] for ts in sorted(captures)]


class WaybackClient:
    """Lists and fetches archived captures of a URL."""

    def __init__(
        self, fetcher: Fetcher, *, http: httpx.AsyncClient | None = None, min_interval_s: float = 1.5
    ) -> None:
        self._fetcher = fetcher
        self._owns_http = http is None
        self._http = (
            http
            if http is not None
            else httpx.AsyncClient(
                timeout=httpx.Timeout(60.0, connect=15.0), headers={"User-Agent": fetcher.user_agent}
            )
        )
        self.min_interval_s = min_interval_s
        self._lock = asyncio.Lock()
        self._last_request: float | None = None

    async def aclose(self) -> None:
        if self._owns_http:
            await self._http.aclose()

    async def _pace(self) -> None:
        """Keep at least ``min_interval_s`` between requests to the archive (lock held)."""
        if self._last_request is not None:
            wait = self._last_request + self.min_interval_s - time.monotonic()
            if wait > 0:
                await asyncio.sleep(wait)

    async def list_captures(
        self,
        url: str,
        *,
        since: date | None = None,
        until: date | None = None,
        per: Literal["month", "day", "all"] = "month",
        limit: int = 24,
    ) -> list[ArchiveCapture]:
        """Successful (HTTP 200) captures of ``url``, oldest first.

        ``per="month"`` keeps the first capture of each month, ``"day"`` the first of each
        day, ``"all"`` everything; ``limit`` caps the number of rows the archive returns.
        """
        params: dict[str, str | int] = {
            "url": url,
            "output": "json",
            "fl": "timestamp,original,statuscode,digest,length",
            "filter": "statuscode:200",
        }
        if per in _COLLAPSE:
            params["collapse"] = _COLLAPSE[per]
        if since is not None:
            params["from"] = since.strftime("%Y%m%d")
        if until is not None:
            params["to"] = until.strftime("%Y%m%d")
        if limit:
            params["limit"] = limit

        headers = {"User-Agent": self._fetcher.user_agent}
        last_problem = "no attempt made"
        for attempt in range(len(_RETRY_DELAYS_S) + 1):
            async with self._lock:
                await self._pace()
                try:
                    response = await self._http.get(CDX_ENDPOINT, params=params, headers=headers)
                except httpx.HTTPError as exc:
                    response = None
                    last_problem = f"{type(exc).__name__}: {exc}"
                finally:
                    self._last_request = time.monotonic()
            if response is not None:
                status = response.status_code
                if status == 200:
                    if not response.content.strip():
                        return []
                    try:
                        payload = response.json()
                    except ValueError as exc:
                        raise WaybackError(f"CDX returned invalid JSON: {response.text[:200]!r}") from exc
                    return _parse_cdx(payload)
                if status != 429 and status < 500:
                    raise WaybackError(f"CDX query failed with HTTP {status}: {response.text[:200]!r}")
                last_problem = f"HTTP {status}"
            if attempt < len(_RETRY_DELAYS_S):
                delay = _RETRY_DELAYS_S[attempt]
                logger.warning("wayback CDX: %s - retrying in %.0fs", last_problem, delay)
                await _sleep(delay)
        raise WaybackError(f"CDX query for {url} failed after retries: {last_problem}")

    async def closest_capture(self, url: str, when: date) -> ArchiveCapture | None:
        """The capture closest to ``when`` via the Availability API, or None (never raises).

        A fallback for when CDX is overloaded (it answers 503 for minutes at a time): the
        availability endpoint is a different, lighter service. Single attempt, no retries.
        """
        async with self._lock:
            await self._pace()
            try:
                response = await self._http.get(AVAILABILITY_ENDPOINT,
                                                params={"url": url, "timestamp": when.strftime("%Y%m%d")})
            except httpx.HTTPError as exc:
                logger.info("wayback availability failed for %s: %s", url, exc)
                return None
            finally:
                self._last_request = time.monotonic()
        if response.status_code != 200:
            return None
        try:
            closest = (response.json().get("archived_snapshots") or {}).get("closest") or {}
        except (ValueError, AttributeError):
            return None
        timestamp = str(closest.get("timestamp") or "")
        if not closest.get("available") or str(closest.get("status") or "200") != "200" or len(timestamp) < 8:
            return None
        original = str(closest.get("url") or "").split(f"/{timestamp}/", 1)[-1] or url
        captures = _parse_cdx([["timestamp", "original", "statuscode"], [timestamp, original, "200"]])
        return captures[0] if captures else None

    async def fetch_capture(self, capture: ArchiveCapture) -> FetchResult:
        """Fetch the capture's original bytes via the Fetcher (never raises).

        robots.txt is not consulted: the archive is a public service meant for exactly this
        use, and the page's own robots.txt applies to the live site, not the archive. The
        Fetcher's per-host spacing still applies on top of this client's own pacing.
        """
        async with self._lock:
            await self._pace()
            try:
                return await self._fetcher.fetch(capture.raw_url, check_robots=False)
            finally:
                self._last_request = time.monotonic()
