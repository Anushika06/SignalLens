"""Provider-neutral web/news search interface.

Search results are the Verifier's and the Planner's window onto the web. Whatever the
provider, results come back as :class:`SearchResult` with a timezone-aware UTC
``published_at`` (when known) and a ``publisher`` key used to decide publisher
independence (C4). Results are deduplicated by normalised URL and capped at
``max_results``.

HTTP providers share :class:`HTTPSearchProvider`'s retry policy (the same as the LLM
providers): 429, 5xx, timeouts and connection errors are retried with backoff (1 s, 3 s;
``retry-after`` honoured up to 20 s), then raise ``SearchError(retryable=True)``; other
4xx raise ``SearchError(retryable=False)`` immediately.
"""

from __future__ import annotations

import asyncio
import logging
import re
from abc import ABC, abstractmethod
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import Any, ClassVar, Literal

import httpx
from dateutil import parser as date_parser

from signallens.util.urls import host_of, normalize_url, publisher_key

__all__ = [
    "HTTPSearchProvider",
    "SearchError",
    "SearchProvider",
    "SearchResult",
    "SearchTopic",
    "as_list",
    "clean_domains",
    "finalize_results",
    "make_snippet",
    "parse_published_date",
]

logger = logging.getLogger(__name__)

# Indirection so tests can replace backoff sleeps without touching asyncio globally.
_sleep = asyncio.sleep

SearchTopic = Literal["general", "news"]


@dataclass
class SearchResult:
    url: str
    title: str
    snippet: str
    published_at: datetime | None = None  # timezone-aware UTC when known
    publisher: str = ""  # publisher_key(url); filled in automatically when empty
    score: float | None = None
    content: str | None = None  # extended text if the provider returned it
    provider: str = ""

    def __post_init__(self) -> None:
        if not self.publisher:
            self.publisher = publisher_key(self.url)
        if self.published_at is not None:
            if self.published_at.tzinfo is None:
                self.published_at = self.published_at.replace(tzinfo=UTC)
            else:
                self.published_at = self.published_at.astimezone(UTC)


class SearchError(Exception):
    """A search call failed; ``retryable`` says whether trying later can help."""

    def __init__(self, message: str, *, retryable: bool = False, status: int | None = None) -> None:
        super().__init__(message)
        self.retryable = retryable
        self.status = status


class SearchProvider(ABC):
    """Interface every search backend implements (real providers and test fakes)."""

    name: str = "search"

    @abstractmethod
    async def search(
        self,
        query: str,
        *,
        max_results: int = 8,
        recency_days: int | None = None,
        include_domains: list[str] | None = None,
        topic: SearchTopic = "general",
    ) -> list[SearchResult]:
        """Return at most ``max_results`` deduplicated results for ``query``."""

    async def aclose(self) -> None:
        """Release network resources. Safe to call more than once."""
        return None

    async def __aenter__(self) -> SearchProvider:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()


# --------------------------------------------------------------------------- helpers


def finalize_results(results: Iterable[SearchResult], max_results: int) -> list[SearchResult]:
    """Drop URL-less results and duplicates (by normalised URL); keep the first ``max_results``."""
    seen: set[str] = set()
    out: list[SearchResult] = []
    for result in results:
        if len(out) >= max_results:
            break
        if not result.url:
            continue
        key = normalize_url(result.url)
        if key in seen:
            continue
        seen.add(key)
        out.append(result)
    return out


def clean_domains(domains: Iterable[str]) -> list[str]:
    """``https://www.razorpay.com/x`` -> ``razorpay.com``; empties and duplicates dropped."""
    out: list[str] = []
    for domain in domains:
        host = host_of(domain)
        if host.startswith("www."):
            host = host[4:]
        if host and host not in out:
            out.append(host)
    return out


def make_snippet(text: str | None, limit: int = 300) -> str:
    """First ~``limit`` characters of ``text`` on a word boundary, whitespace collapsed."""
    if not text:
        return ""
    flat = " ".join(text.split())
    if len(flat) <= limit:
        return flat
    cut = flat[:limit]
    space = cut.rfind(" ")
    if space > limit * 0.6:
        cut = cut[:space]
    return cut.rstrip(" ,;:") + "…"


_RELATIVE = re.compile(
    r"^(?P<n>\d+|an?|one)\s*(?P<unit>s|secs?|seconds?|m|mins?|minutes?|h|hrs?|hours?|d|days?"
    r"|w|wks?|weeks?|mos?|months?|y|yrs?|years?)\s+ago$",
    re.IGNORECASE,
)
# fmt: off
_UNIT_SECONDS = {
    "s": 1, "sec": 1, "secs": 1, "second": 1, "seconds": 1,
    "m": 60, "min": 60, "mins": 60, "minute": 60, "minutes": 60,
    "h": 3600, "hr": 3600, "hrs": 3600, "hour": 3600, "hours": 3600,
    "d": 86400, "day": 86400, "days": 86400,
    "w": 604800, "wk": 604800, "wks": 604800, "week": 604800, "weeks": 604800,
    "mo": 2592000, "mos": 2592000, "month": 2592000, "months": 2592000,
    "y": 31536000, "yr": 31536000, "yrs": 31536000, "year": 31536000, "years": 31536000,
}
# fmt: on


def parse_published_date(value: Any, *, now: datetime | None = None) -> datetime | None:
    """Parse a provider date string into a timezone-aware UTC datetime, or ``None``.

    Handles ISO 8601, RFC 2822 ("Sun, 21 Sep 2026 10:15:00 GMT"), written dates
    ("Sep 21, 2026") and relative ages ("3 hours ago", "2 days ago", "yesterday").
    Naive values are taken as UTC. Dates in the future are rejected as misparses.
    """
    if not isinstance(value, str):
        return None
    s = value.strip()
    if not s:
        return None
    now = now or datetime.now(UTC)
    lowered = s.lower()
    if lowered in {"today", "just now"}:
        return now
    if lowered == "yesterday":
        return now - timedelta(days=1)
    match = _RELATIVE.match(s)
    if match:
        n_raw = match.group("n").lower()
        n = 1 if n_raw in {"a", "an", "one"} else int(n_raw)
        return now - timedelta(seconds=n * _UNIT_SECONDS[match.group("unit").lower()])
    if not any(c.isdigit() for c in s):  # dateutil would happily turn "Monday" into a date
        return None
    parsed: datetime | None = None
    try:
        parsed = parsedate_to_datetime(s)
    except (TypeError, ValueError, IndexError):
        parsed = None
    if parsed is None:
        try:
            parsed = date_parser.parse(s)
        except (ValueError, OverflowError, TypeError):
            return None
    parsed = parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)
    if parsed > now + timedelta(days=1):
        if not re.search(r"\b\d{4}\b", s):  # "Dec 30" read in January: it meant last year
            try:
                parsed = parsed.replace(year=parsed.year - 1)
            except ValueError:
                return None
        if parsed > now + timedelta(days=1):
            return None
    return parsed


def _parse_retry_after(headers: httpx.Headers) -> float | None:
    raw = headers.get("retry-after")
    if not raw:
        return None
    try:
        return max(0.0, float(raw))
    except ValueError:
        pass
    try:
        when = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    return max(0.0, (when - datetime.now(UTC)).total_seconds())


class HTTPSearchProvider(SearchProvider):
    """Shared plumbing for JSON-over-HTTPS search APIs: client, retries, errors."""

    retry_backoff_s: ClassVar[tuple[float, ...]] = (1.0, 3.0)
    max_retry_after_s: ClassVar[float] = 20.0

    def __init__(
        self,
        api_key: str,
        *,
        timeout_s: float = 30.0,
        max_retries: int = 2,
        http: httpx.AsyncClient | None = None,
    ) -> None:
        self._api_key = api_key
        self.timeout_s = timeout_s
        self.max_retries = max(0, max_retries)
        self._timeout = httpx.Timeout(timeout_s, connect=min(timeout_s, 10.0))
        self._owns_http = http is None
        self._http = http if http is not None else httpx.AsyncClient(timeout=self._timeout)

    def __repr__(self) -> str:  # never show the key
        return f"{type(self).__name__}()"

    async def aclose(self) -> None:
        if self._owns_http:
            await self._http.aclose()

    def _redact(self, text: str) -> str:
        if self._api_key and len(self._api_key) >= 6:
            text = text.replace(self._api_key, "***")
        return text

    def _retry_delay(self, attempt: int, retry_after: float | None) -> float:
        if retry_after is not None:
            return min(retry_after, self.max_retry_after_s)
        backoff = self.retry_backoff_s
        if attempt < len(backoff):
            return backoff[attempt]
        return min(backoff[-1] * 3 ** (attempt - len(backoff) + 1), self.max_retry_after_s)

    def _error_detail(self, response: httpx.Response) -> str:
        detail = ""
        try:
            body = response.json()
        except ValueError:
            body = None
        if isinstance(body, dict):
            for key in ("detail", "error", "message"):
                value = body.get(key)
                if isinstance(value, dict):
                    value = value.get("error") or value.get("message")
                if isinstance(value, str) and value:
                    detail = value
                    break
        if not detail:
            detail = response.text[:300]
        return self._redact(" ".join(detail.split()))[:500]

    async def _post_json(
        self, url: str, *, headers: dict[str, str], payload: dict[str, Any]
    ) -> dict[str, Any]:
        """POST ``payload`` and return the decoded JSON body, retrying transient failures."""
        attempts = self.max_retries + 1
        last_error: SearchError | None = None
        for attempt in range(attempts):
            retry_after: float | None = None
            try:
                response = await self._http.post(url, headers=headers, json=payload, timeout=self._timeout)
            except httpx.TimeoutException:
                last_error = SearchError(
                    f"{self.name}: request timed out after {self.timeout_s:g}s", retryable=True
                )
            except httpx.TransportError as exc:
                last_error = SearchError(
                    f"{self.name}: connection error ({type(exc).__name__}): {self._redact(str(exc))[:200]}",
                    retryable=True,
                )
            else:
                status = response.status_code
                if 200 <= status < 300:
                    try:
                        body = response.json()
                    except ValueError:
                        body = None
                    if isinstance(body, dict):
                        return body
                    last_error = SearchError(
                        f"{self.name}: HTTP {status} with a non-JSON body", retryable=True, status=status
                    )
                elif status == 429 or status >= 500:
                    retry_after = _parse_retry_after(response.headers)
                    last_error = SearchError(
                        f"{self.name}: HTTP {status}: {self._error_detail(response)}",
                        retryable=True,
                        status=status,
                    )
                else:
                    raise SearchError(
                        f"{self.name}: HTTP {status}: {self._error_detail(response)}",
                        retryable=False,
                        status=status,
                    )
            if attempt + 1 >= attempts:
                break
            delay = self._retry_delay(attempt, retry_after)
            logger.warning(
                "%s: %s - retrying in %.1fs (attempt %d/%d)",
                self.name,
                last_error,
                delay,
                attempt + 2,
                attempts,
            )
            await _sleep(delay)
        assert last_error is not None
        raise last_error


def as_list(value: Any) -> Sequence[Any]:
    """Provider JSON arrays, tolerating ``null``/missing values."""
    return value if isinstance(value, list) else []
