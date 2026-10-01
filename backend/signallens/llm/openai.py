"""OpenAI Chat Completions provider (plain HTTPS), also usable with compatible servers.

Point ``base_url`` at any OpenAI-compatible endpoint (a local Ollama at
``http://localhost:11434/v1``, vLLM, LM Studio...) to use it instead; an empty ``api_key``
sends no ``Authorization`` header. Structured output uses ``response_format`` with a
non-strict JSON schema, and the JSON is parsed tolerantly because compatible servers do not
always honour it.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from signallens.llm.base import ChatMessage, HTTPLLMProvider, LLMError, LLMResult, LLMUsage, parse_json_object
from signallens.llm.schema_utils import inline_refs, safe_schema_name

__all__ = ["OpenAIProvider", "is_reasoning_model"]

logger = logging.getLogger(__name__)

_REASONING_PREFIXES = ("gpt-5", "o1", "o3", "o4")


def is_reasoning_model(model: str) -> bool:
    """Reasoning families reject ``temperature``; ``org/gpt-5-mini`` style ids are handled."""
    return model.rsplit("/", 1)[-1].lower().startswith(_REASONING_PREFIXES)


def _content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):  # some compatible servers return content parts
        return "".join(str(p.get("text") or "") for p in content if isinstance(p, dict))
    return ""


class OpenAIProvider(HTTPLLMProvider):
    """``POST {base_url}/chat/completions`` with bearer auth."""

    name = "openai"
    default_base_url = "https://api.openai.com/v1"

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
    ) -> LLMResult:
        started = time.perf_counter()
        chat: list[dict[str, str]] = []
        if system:
            chat.append({"role": "system", "content": system})
        chat.extend({"role": m.role, "content": m.content} for m in messages)
        payload: dict[str, Any] = {"model": model, "messages": chat, "max_completion_tokens": max_tokens}
        if temperature is not None and not is_reasoning_model(model):
            payload["temperature"] = temperature
        if json_schema is not None:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": safe_schema_name(schema_name),
                    "schema": inline_refs(json_schema),
                    "strict": False,
                },
            }

        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        body = await self._post_json(f"{self.base_url}/chat/completions", headers=headers, payload=payload)

        choices = body.get("choices") or []
        if not choices or not isinstance(choices[0], dict):
            raise LLMError("openai: response contained no choices", retryable=True)
        choice = choices[0]
        message = choice.get("message") or {}
        text = _content_text(message.get("content"))
        stop_reason = choice.get("finish_reason")
        refusal = message.get("refusal")
        if not text and refusal:
            raise LLMError(f"openai: model refused: {str(refusal)[:200]}", retryable=False)

        data: dict[str, Any] | None = None
        if json_schema is not None:
            data = parse_json_object(text)
            if data is None:
                raise LLMError(
                    f"openai: output is not a JSON object (finish_reason={stop_reason}): {text[:200]!r}",
                    retryable=True,
                )

        usage = body.get("usage") or {}
        return LLMResult(
            text=text,
            data=data,
            usage=LLMUsage(
                input_tokens=int(usage.get("prompt_tokens") or 0),
                output_tokens=int(usage.get("completion_tokens") or 0),
            ),
            model=str(body.get("model") or model),
            provider=self.name,
            latency_ms=int((time.perf_counter() - started) * 1000),
            stop_reason=stop_reason,
        )
