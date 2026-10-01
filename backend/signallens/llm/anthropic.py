"""Anthropic Messages API provider (plain HTTPS).

Structured output uses forced tool use: the JSON schema becomes the ``input_schema`` of a
single tool and ``tool_choice`` forces the model to call it, so the parsed object arrives as
the tool call's ``input`` - no free-text JSON parsing needed in the normal case.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from signallens.llm.base import ChatMessage, HTTPLLMProvider, LLMError, LLMResult, LLMUsage, parse_json_object
from signallens.llm.schema_utils import inline_refs, safe_schema_name

__all__ = ["AnthropicProvider"]

logger = logging.getLogger(__name__)


class AnthropicProvider(HTTPLLMProvider):
    """``POST {base_url}/v1/messages`` with ``x-api-key`` auth."""

    name = "anthropic"
    default_base_url = "https://api.anthropic.com"
    api_version = "2023-06-01"

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
        started = time.perf_counter()
        payload: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
        }
        if system:
            payload["system"] = system
        if temperature is not None:
            payload["temperature"] = temperature
        tool_name = safe_schema_name(schema_name)
        if json_schema is not None:
            payload["tools"] = [
                {
                    "name": tool_name,
                    "description": "Return the result",
                    "input_schema": inline_refs(json_schema),
                }
            ]
            payload["tool_choice"] = {"type": "tool", "name": tool_name}

        headers = {
            "x-api-key": self._api_key,
            "anthropic-version": self.api_version,
            "content-type": "application/json",
        }
        body = await self._post_json(f"{self.base_url}/v1/messages", headers=headers, payload=payload)

        blocks = [b for b in body.get("content") or [] if isinstance(b, dict)]
        text = "".join(str(b.get("text") or "") for b in blocks if b.get("type") == "text")
        stop_reason = body.get("stop_reason")
        data: dict[str, Any] | None = None
        if json_schema is not None:
            tool_calls = [b for b in blocks if b.get("type") == "tool_use"]
            call = next(
                (b for b in tool_calls if b.get("name") == tool_name), tool_calls[0] if tool_calls else None
            )
            if call is not None and isinstance(call.get("input"), dict):
                data = call["input"]
                text = json.dumps(data, ensure_ascii=False)
            else:
                # Defensive: a proxy or older model may answer in text instead of the tool.
                data = parse_json_object(text)
                if data is None:
                    raise LLMError(
                        f"anthropic: no structured output (stop_reason={stop_reason}); text: {text[:200]!r}",
                        retryable=True,
                    )

        usage = body.get("usage") or {}
        return LLMResult(
            text=text,
            data=data,
            usage=LLMUsage(
                input_tokens=int(usage.get("input_tokens") or 0),
                output_tokens=int(usage.get("output_tokens") or 0),
            ),
            model=str(body.get("model") or model),
            provider=self.name,
            latency_ms=int((time.perf_counter() - started) * 1000),
            stop_reason=stop_reason,
        )
