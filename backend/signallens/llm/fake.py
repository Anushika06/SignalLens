"""Scripted LLM for tests: deterministic answers, full call recording, no network.

Two ways to script it::

    # 1. A list of responses, consumed in order
    llm = ScriptedLLM([
        {"material": True, "reason": "price cut"},   # dict -> result.data (+ JSON text)
        "Plain text answer",                         # str  -> result.text
        LLMError("rate limited", retryable=True),    # exception -> raised
    ])

    # 2. A handler that decides per call (sync or async)
    def handler(system, messages, json_schema, schema_name):
        if schema_name == "triage":
            return {"material": False}
        return "ok"
    llm = ScriptedLLM(handler)

Every call is appended to ``llm.calls`` as a dict with ``model``, ``system``,
``messages``, ``json_schema``, ``schema_name``, ``max_tokens`` and ``temperature``.

Behaviour mirrors real providers where it matters: when a ``json_schema`` is given, a
``str`` response is parsed like model output (fences and prose tolerated) and an
unparseable one raises ``LLMError(retryable=True)``. An ``LLMResult`` is returned as-is.
Running out of scripted responses raises :class:`ScriptExhaustedError`, an
``AssertionError``, so an unexpected extra model call fails the test loudly.
"""

from __future__ import annotations

import copy
import inspect
import json
from collections import deque
from collections.abc import Awaitable, Callable, Sequence
from typing import Any

from signallens.llm.base import ChatMessage, LLMError, LLMProvider, LLMResult, LLMUsage, parse_json_object

__all__ = ["ScriptExhaustedError", "ScriptedLLM", "ScriptedResponse"]

ScriptedResponse = dict[str, Any] | str | LLMResult | BaseException
Handler = Callable[
    [str, list[ChatMessage], dict[str, Any] | None, str],
    ScriptedResponse | Awaitable[ScriptedResponse],
]


class ScriptExhaustedError(AssertionError):
    """The code under test made more model calls than the test scripted."""


def _estimate_tokens(chars: int) -> int:
    """Rough token count (~4 characters per token), enough for cost/budget bookkeeping."""
    return (chars + 3) // 4


class ScriptedLLM(LLMProvider):
    """An :class:`LLMProvider` that answers from a script or a handler function."""

    name = "scripted"

    def __init__(self, script: Sequence[ScriptedResponse] | Handler) -> None:
        self._handler: Handler | None = None
        self._queue: deque[ScriptedResponse] | None = None
        if callable(script):
            self._handler = script
        elif isinstance(script, Sequence) and not isinstance(script, str | bytes):
            self._queue = deque(script)
        else:
            raise TypeError("ScriptedLLM expects a list of responses or a handler callable")
        self.calls: list[dict[str, Any]] = []
        self.closed = False

    @property
    def remaining(self) -> int | None:
        """Scripted responses not yet consumed (``None`` in handler mode)."""
        return None if self._queue is None else len(self._queue)

    @property
    def last_call(self) -> dict[str, Any]:
        if not self.calls:
            raise AssertionError("ScriptedLLM was never called")
        return self.calls[-1]

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
        self.calls.append(
            {
                "model": model,
                "system": system,
                "messages": list(messages),
                "json_schema": json_schema,
                "schema_name": schema_name,
                "max_tokens": max_tokens,
                "temperature": temperature,
            }
        )
        response = await self._next_response(system, list(messages), json_schema, schema_name)
        if isinstance(response, BaseException):
            raise response
        if isinstance(response, LLMResult):
            return response

        if isinstance(response, dict):
            data: dict[str, Any] | None = copy.deepcopy(response)
            text = json.dumps(response, ensure_ascii=False)
        elif isinstance(response, str):
            text = response
            data = None
            if json_schema is not None:
                data = parse_json_object(text)
                if data is None:
                    raise LLMError(f"scripted: response is not a JSON object: {text[:200]!r}", retryable=True)
        else:
            raise TypeError(
                f"ScriptedLLM cannot return {type(response).__name__}; use dict, str or LLMResult"
            )

        prompt_chars = len(system) + sum(len(m.content) for m in messages)
        return LLMResult(
            text=text,
            data=data,
            usage=LLMUsage(
                input_tokens=_estimate_tokens(prompt_chars), output_tokens=_estimate_tokens(len(text))
            ),
            model=model,
            provider=self.name,
            latency_ms=0,
            stop_reason="end_turn",
        )

    async def _next_response(
        self, system: str, messages: list[ChatMessage], json_schema: dict[str, Any] | None, schema_name: str
    ) -> ScriptedResponse:
        if self._handler is not None:
            out = self._handler(system, messages, json_schema, schema_name)
            if inspect.isawaitable(out):
                out = await out
            return out
        assert self._queue is not None
        if not self._queue:
            scripted = len(self.calls) - 1
            preview = messages[-1].content[:120] if messages else ""
            raise ScriptExhaustedError(
                f"ScriptedLLM script exhausted: {scripted} response(s) were scripted but call "
                f"#{len(self.calls)} arrived (schema_name={schema_name!r}, last message={preview!r})"
            )
        return self._queue.popleft()

    async def aclose(self) -> None:
        self.closed = True
