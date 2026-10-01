"""Google Gemini ``generateContent`` provider (plain HTTPS).

Structured output uses ``responseMimeType: application/json`` plus ``responseJsonSchema``
(refs inlined; ``title`` / ``default`` / ``examples`` stripped). Some models and API
versions reject parts of a schema with HTTP 400; in that case the call is retried once
without ``responseJsonSchema`` and the schema is given to the model as text instead, which
keeps the pipeline working at the cost of slightly weaker guarantees.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from signallens.llm.base import ChatMessage, HTTPLLMProvider, LLMError, LLMResult, LLMUsage, parse_json_object
from signallens.llm.schema_utils import inline_refs, strip_keys

__all__ = ["GeminiProvider"]

logger = logging.getLogger(__name__)

_BLOCKED_FINISH = frozenset({"SAFETY", "RECITATION", "PROHIBITED_CONTENT", "BLOCKLIST", "SPII"})


class GeminiProvider(HTTPLLMProvider):
    """``POST {base_url}/models/{model}:generateContent`` with ``x-goog-api-key`` auth."""

    name = "gemini"
    default_base_url = "https://generativelanguage.googleapis.com/v1beta"

    def _payload(
        self,
        *,
        system: str,
        messages: list[ChatMessage],
        schema: dict[str, Any] | None,
        schema_in_prompt: bool,
        max_tokens: int,
        temperature: float | None,
    ) -> dict[str, Any]:
        config: dict[str, Any] = {"maxOutputTokens": max_tokens}
        if temperature is not None:
            config["temperature"] = temperature
        if schema is not None:
            config["responseMimeType"] = "application/json"
            if not schema_in_prompt:
                config["responseJsonSchema"] = schema
        instruction = system
        if schema is not None and schema_in_prompt:
            instruction = (
                f"{system}\n\nRespond with a single JSON object that conforms to this JSON Schema:\n"
                f"{json.dumps(schema, ensure_ascii=False)}"
            ).strip()
        payload: dict[str, Any] = {
            "contents": [
                {"role": "model" if m.role == "assistant" else "user", "parts": [{"text": m.content}]}
                for m in messages
            ],
            "generationConfig": config,
        }
        if instruction:
            payload["systemInstruction"] = {"parts": [{"text": instruction}]}
        return payload

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
        schema = (
            strip_keys(inline_refs(json_schema), {"title", "default", "examples"})
            if json_schema is not None
            else None
        )
        model_id = model.removeprefix("models/")
        url = f"{self.base_url}/models/{model_id}:generateContent"
        headers = {"x-goog-api-key": self._api_key, "Content-Type": "application/json"}
        common = {
            "system": system,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        payload = self._payload(schema=schema, schema_in_prompt=False, **common)
        try:
            body = await self._post_json(url, headers=headers, payload=payload)
        except LLMError as exc:
            if schema is None or exc.status != 400 or "schema" not in str(exc).lower():
                raise
            logger.warning("gemini: schema rejected (%s); retrying with the schema in the prompt", exc)
            payload = self._payload(schema=schema, schema_in_prompt=True, **common)
            body = await self._post_json(url, headers=headers, payload=payload)

        candidates = body.get("candidates") or []
        if not candidates:
            block_reason = (body.get("promptFeedback") or {}).get("blockReason")
            raise LLMError(
                f"gemini: no candidates returned (blockReason={block_reason})", retryable=block_reason is None
            )
        candidate = candidates[0]
        parts = (candidate.get("content") or {}).get("parts") or []
        # Thinking models may include thought summaries; they are not the answer.
        text = "".join(
            str(p.get("text") or "") for p in parts if isinstance(p, dict) and not p.get("thought")
        )
        stop_reason = candidate.get("finishReason")
        if not text and stop_reason in _BLOCKED_FINISH:
            raise LLMError(f"gemini: response blocked (finishReason={stop_reason})", retryable=False)

        data: dict[str, Any] | None = None
        if schema is not None:
            data = parse_json_object(text)
            if data is None:
                raise LLMError(
                    f"gemini: output is not a JSON object (finishReason={stop_reason}): {text[:200]!r}",
                    retryable=True,
                )

        meta = body.get("usageMetadata") or {}
        return LLMResult(
            text=text,
            data=data,
            usage=LLMUsage(
                input_tokens=int(meta.get("promptTokenCount") or 0),
                # Thinking tokens are billed as output, so they count here.
                output_tokens=int(meta.get("candidatesTokenCount") or 0)
                + int(meta.get("thoughtsTokenCount") or 0),
            ),
            model=str(body.get("modelVersion") or model_id),
            provider=self.name,
            latency_ms=int((time.perf_counter() - started) * 1000),
            stop_reason=stop_reason,
        )
