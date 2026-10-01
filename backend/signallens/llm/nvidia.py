"""NVIDIA NIM provider: hosted open models behind NVIDIA's OpenAI-compatible API.

``https://integrate.api.nvidia.com/v1`` speaks the Chat Completions schema, so this reuses
:class:`OpenAIProvider` and only changes what NIM needs: its base URL, a ``nvidia`` name in
errors and traces, a response schema in which every property is required (see
:func:`require_all_properties` — without it, guided decoding drops optional fields), and the
``enable_thinking`` switch. Nemotron reasons in hidden tokens by default: 500-2,600 of them
per call, which turns a 1-second extraction into 30-60 seconds and can exhaust a small
``max_tokens`` before any JSON is written. The gateway turns thinking off where it does not
pay for itself.

The free developer tier allows about 40 requests per minute per key and queues requests at
busy times, so callers keep concurrency low and timeouts generous.
"""

from __future__ import annotations

from typing import Any

from signallens.llm.openai import OpenAIProvider
from signallens.llm.schema_utils import require_all_properties

__all__ = ["NVIDIA_BASE_URL", "NvidiaProvider"]

NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"


class NvidiaProvider(OpenAIProvider):
    name = "nvidia"
    default_base_url = NVIDIA_BASE_URL

    def _prepare_schema(self, schema: dict[str, Any]) -> dict[str, Any]:
        return require_all_properties(schema)

    def _extra_payload(self, *, thinking: bool | None) -> dict[str, Any]:
        if thinking is None:
            return {}
        return {"chat_template_kwargs": {"enable_thinking": thinking}}
