"""Provider-neutral LLM interface.

Every model call in SignalLens goes through :meth:`LLMProvider.generate`, which returns an
:class:`LLMResult`: the raw text, the parsed JSON object when a JSON schema was requested,
token usage and latency - exactly what a Run step records ("show your work", C13).

Real providers speak plain HTTPS via ``httpx`` (no vendor SDKs) on top of
:class:`HTTPLLMProvider`, which owns the shared retry policy: HTTP 429, 5xx, timeouts and
connection errors are retried with backoff (1 s, 3 s; a ``retry-after`` header is honoured up
to 20 s) and then surface as ``LLMError(retryable=True)``; any other 4xx fails fast as
``LLMError(retryable=False)`` carrying the provider's own error message. API keys never
appear in errors or logs.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any, ClassVar, Literal

import httpx

__all__ = [
    "ChatMessage",
    "HTTPLLMProvider",
    "LLMError",
    "LLMProvider",
    "LLMResult",
    "LLMUsage",
    "Role",
    "parse_json_object",
]

logger = logging.getLogger(__name__)

# Indirection so tests can replace backoff sleeps without touching asyncio globally.
_sleep = asyncio.sleep

Role = Literal["user", "assistant"]


@dataclass
class ChatMessage:
    role: Role
    content: str


@dataclass
class LLMUsage:
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass
class LLMResult:
    text: str  # raw text output (JSON string when json_schema given)
    data: dict[str, Any] | None  # parsed JSON object when json_schema given, else None
    usage: LLMUsage
    model: str
    provider: str
    latency_ms: int
    stop_reason: str | None = None


class LLMError(Exception):
    """A model call failed.

    ``retryable`` tells the caller whether trying again later can help (rate limits,
    outages, unparseable output); ``status`` is the HTTP status when there was one.
    """

    def __init__(self, message: str, *, retryable: bool = False, status: int | None = None) -> None:
        super().__init__(message)
        self.retryable = retryable
        self.status = status


class LLMProvider(ABC):
    """Interface every model backend implements (real providers and test fakes)."""

    name: str = "llm"

    @abstractmethod
    async def generate(
        self,
        *,
        model: str,
        system: str,
        messages: list[ChatMessage],
        json_schema: dict[str, Any] | None = None,
        schema_name: str = "output",
        max_tokens: int = 4096,
        temperature: float | None = None,
        thinking: bool | None = None,
    ) -> LLMResult:
        """Run one completion.

        With ``json_schema`` the provider uses its native structured-output mechanism and
        the result's ``data`` is the parsed JSON object (never ``None``). ``thinking`` asks
        models with a switchable reasoning mode to turn it on or off; ``None`` keeps the
        model's default, and providers without such a switch ignore it.
        """

    async def aclose(self) -> None:
        """Release network resources. Safe to call more than once."""
        return None

    async def __aenter__(self) -> LLMProvider:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()


_FENCE = re.compile(r"```[a-zA-Z0-9_-]*\s*\n?(.*?)```", re.DOTALL)


def parse_json_object(text: str) -> dict[str, Any] | None:
    """Extract the first top-level JSON object from model output, or ``None``.

    Tolerates the usual model habits: code fences (```json ... ```), and prose before or
    after the object.
    """
    s = text.strip()
    if not s:
        return None
    try:
        obj = json.loads(s)
    except ValueError:
        pass
    else:
        return obj if isinstance(obj, dict) else None
    for match in _FENCE.finditer(s):
        try:
            obj = json.loads(match.group(1).strip())
        except ValueError:
            continue
        if isinstance(obj, dict):
            return obj
    decoder = json.JSONDecoder()
    start = s.find("{")
    attempts = 0
    while start != -1 and attempts < 200:
        try:
            obj, _ = decoder.raw_decode(s, start)
        except ValueError:
            pass
        else:
            if isinstance(obj, dict):
                return obj
        start = s.find("{", start + 1)
        attempts += 1
    return None


def _parse_retry_after(headers: httpx.Headers) -> float | None:
    """Seconds to wait according to ``retry-after-ms`` / ``retry-after`` (secs or HTTP date)."""
    raw_ms = headers.get("retry-after-ms")
    if raw_ms:
        try:
            return max(0.0, float(raw_ms) / 1000.0)
        except ValueError:
            pass
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


class HTTPLLMProvider(LLMProvider):
    """Shared plumbing for providers that speak JSON over HTTPS: client, retries, errors."""

    default_base_url: ClassVar[str] = ""
    #: Delay before retry 1, 2, ...; later retries keep tripling, capped at max_retry_after_s.
    retry_backoff_s: ClassVar[tuple[float, ...]] = (1.0, 3.0)
    max_retry_after_s: ClassVar[float] = 20.0

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str | None = None,
        timeout_s: float = 120.0,
        max_retries: int = 2,
        http: httpx.AsyncClient | None = None,
    ) -> None:
        self._api_key = api_key
        self.base_url = (base_url or self.default_base_url).rstrip("/")
        self.timeout_s = timeout_s
        self.max_retries = max(0, max_retries)
        self._timeout = httpx.Timeout(timeout_s, connect=min(timeout_s, 15.0))
        self._owns_http = http is None
        self._http = http if http is not None else httpx.AsyncClient(timeout=self._timeout)

    def __repr__(self) -> str:  # never show the key
        return f"{type(self).__name__}(base_url={self.base_url!r})"

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
        """The provider's own error message (all three use ``{"error": {"message": ...}}``)."""
        detail = ""
        try:
            body = response.json()
        except ValueError:
            body = None
        if isinstance(body, dict):
            error = body.get("error")
            if isinstance(error, dict):
                detail = str(error.get("message") or error.get("type") or "")
            elif isinstance(error, str):
                detail = error
            if not detail and isinstance(body.get("message"), str):
                detail = body["message"]
        if not detail:
            detail = response.text[:300]
        return self._redact(" ".join(detail.split()))[:500]

    async def _post_json(
        self, url: str, *, headers: dict[str, str], payload: dict[str, Any]
    ) -> dict[str, Any]:
        """POST ``payload`` and return the decoded JSON body, retrying transient failures."""
        attempts = self.max_retries + 1
        last_error: LLMError | None = None
        for attempt in range(attempts):
            retry_after: float | None = None
            try:
                response = await self._http.post(url, headers=headers, json=payload, timeout=self._timeout)
            except httpx.TimeoutException:
                last_error = LLMError(
                    f"{self.name}: request timed out after {self.timeout_s:g}s", retryable=True
                )
            except httpx.TransportError as exc:
                last_error = LLMError(
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
                    last_error = LLMError(
                        f"{self.name}: HTTP {status} with a non-JSON body", retryable=True, status=status
                    )
                elif status == 429 or status >= 500:
                    retry_after = _parse_retry_after(response.headers)
                    last_error = LLMError(
                        f"{self.name}: HTTP {status}: {self._error_detail(response)}",
                        retryable=True,
                        status=status,
                    )
                else:
                    raise LLMError(
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
