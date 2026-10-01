"""LLM providers behind one interface: Anthropic, OpenAI (and compatible servers), Gemini.

Usage::

    from signallens.llm import AnthropicProvider, ChatMessage

    llm = AnthropicProvider(api_key)
    result = await llm.generate(
        model="claude-sonnet-4-5",
        system="You classify page changes.",
        messages=[ChatMessage("user", "...")],
        json_schema=Triage.model_json_schema(),
        schema_name="triage",
    )
    triage = Triage.model_validate(result.data)

Tests use :class:`ScriptedLLM` instead of a real provider.
"""

from signallens.llm.anthropic import AnthropicProvider
from signallens.llm.base import (
    ChatMessage,
    HTTPLLMProvider,
    LLMError,
    LLMProvider,
    LLMResult,
    LLMUsage,
    Role,
    parse_json_object,
)
from signallens.llm.fake import ScriptedLLM, ScriptExhaustedError
from signallens.llm.gemini import GeminiProvider
from signallens.llm.openai import OpenAIProvider, is_reasoning_model
from signallens.llm.schema_utils import inline_refs, safe_schema_name, strip_keys

__all__ = [
    "AnthropicProvider",
    "ChatMessage",
    "GeminiProvider",
    "HTTPLLMProvider",
    "LLMError",
    "LLMProvider",
    "LLMResult",
    "LLMUsage",
    "OpenAIProvider",
    "Role",
    "ScriptExhaustedError",
    "ScriptedLLM",
    "inline_refs",
    "is_reasoning_model",
    "parse_json_object",
    "safe_schema_name",
    "strip_keys",
]
