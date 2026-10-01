"""Model gateway: typed, validated, budgeted model calls.

Agents never call a provider directly. The gateway picks the model for a tier (``fast``
for extraction/triage/materiality, ``reasoning`` for planning/investigation/impact),
asks for JSON matching a Pydantic schema, validates it, gives the model one chance to
repair invalid output, and charges tokens and estimated cost to the run's budget.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, TypeVar

from pydantic import BaseModel, ValidationError

from signallens.llm.base import ChatMessage, LLMError, LLMProvider

if TYPE_CHECKING:
    from signallens.runtime.core import RunContext

log = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)
Tier = Literal["fast", "reasoning"]

# Default models per provider: (fast tier, reasoning tier). Override with SL_LLM_FAST_MODEL /
# SL_LLM_REASONING_MODEL.
DEFAULT_MODELS: dict[str, tuple[str, str]] = {
    # Chosen by benchmarking the NIM catalogue on SignalLens's own extraction and planning
    # schemas (valid JSON, field completeness, latency under the free tier's queueing).
    "nvidia": ("nvidia/nemotron-3-super-120b-a12b", "nvidia/nemotron-3-super-120b-a12b"),
    "anthropic": ("claude-haiku-4-5-20251001", "claude-sonnet-5"),
    "openai": ("gpt-5-mini", "gpt-5"),
    "gemini": ("gemini-2.5-flash", "gemini-2.5-pro"),
    "scripted": ("scripted-fast", "scripted-reasoning"),
}

# Estimated USD per million tokens (input, output), matched by model-name prefix. Used for
# budgets and the cost shown in run traces; update when provider prices change.
PRICES_PER_MTOK: list[tuple[str, tuple[float, float]]] = [
    ("claude-haiku-4-5", (1.0, 5.0)),
    ("claude-sonnet", (3.0, 15.0)),
    ("claude-opus", (5.0, 25.0)),
    ("gpt-5-nano", (0.05, 0.40)),
    ("gpt-5-mini", (0.25, 2.0)),
    ("gpt-5", (1.25, 10.0)),
    ("gemini-2.5-flash-lite", (0.10, 0.40)),
    ("gemini-2.5-flash", (0.30, 2.50)),
    ("gemini-2.5-pro", (1.25, 10.0)),
    ("scripted", (0.0, 0.0)),
    # NVIDIA NIM's hosted developer tier is free (rate-limited), so runs cost nothing.
    ("nvidia/", (0.0, 0.0)),
    ("moonshotai/", (0.0, 0.0)),
    ("deepseek-ai/", (0.0, 0.0)),
    ("z-ai/", (0.0, 0.0)),
    ("openai/gpt-oss", (0.0, 0.0)),
]
FALLBACK_PRICE = (3.0, 15.0)


def price_for(model: str) -> tuple[float, float]:
    for prefix, price in PRICES_PER_MTOK:
        if model.startswith(prefix):
            return price
    return FALLBACK_PRICE


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    pin, pout = price_for(model)
    return (input_tokens * pin + output_tokens * pout) / 1_000_000


# Output ceilings are generous on purpose: reasoning models (GPT-5, Gemini 2.5 Pro) count hidden
# reasoning tokens against the limit, and billing is on actual use, not on the ceiling.


class ModelOutputError(RuntimeError):
    """The model could not produce output matching the schema, even after a repair turn."""


@dataclass
class CallMeta:
    model: str
    input_tokens: int
    output_tokens: int
    latency_ms: int
    cost_usd: float


class ModelGateway:
    def __init__(self, provider: LLMProvider, *, provider_name: str, fast_model: str, reasoning_model: str,
                 thinking_tiers: frozenset[str] | None = None, fallback_models: tuple[str, ...] = (),
                 cooldown_s: float = 300.0):
        self.provider = provider
        self.provider_name = provider_name
        self.fast_model = fast_model
        self.reasoning_model = reasoning_model
        # Hosted free tiers stall one model at a time (a deployment queues for minutes while
        # its neighbours answer instantly), so a failed model is skipped for `cooldown_s` and
        # the call moves on to the next model on the list.
        self.fallback_models = tuple(m for m in fallback_models if m)
        self.cooldown_s = cooldown_s
        self._unhealthy_until: dict[str, float] = {}
        # None = leave each model's default reasoning mode alone; otherwise thinking is switched
        # on for these tiers and off for the rest.
        self.thinking_tiers = thinking_tiers

    def thinking_for(self, tier: Tier) -> bool | None:
        return None if self.thinking_tiers is None else tier in self.thinking_tiers

    def model_for(self, tier: Tier) -> str:
        return self.fast_model if tier == "fast" else self.reasoning_model

    def candidates_for(self, tier: Tier) -> list[str]:
        """The tier's model first, then fallbacks; models in cool-down go last, not away."""
        ordered = list(dict.fromkeys([self.model_for(tier), *self.fallback_models]))
        now = time.monotonic()
        healthy = [m for m in ordered if self._unhealthy_until.get(m, 0.0) <= now]
        return healthy + [m for m in ordered if m not in healthy]

    def mark_unhealthy(self, model: str, seconds: float | None = None) -> None:
        self._unhealthy_until[model] = time.monotonic() + (self.cooldown_s if seconds is None else seconds)

    async def _generate(self, tier: Tier, **kwargs):
        """One completion, failing over across models on outages. Returns (result, model)."""
        candidates = self.candidates_for(tier)
        for i, model in enumerate(candidates):
            try:
                result = await self.provider.generate(model=model, thinking=self.thinking_for(tier), **kwargs)
            except LLMError as e:
                last = i == len(candidates) - 1
                # 404 = model withdrawn for this account; other non-retryable errors are request
                # problems that another model will not fix.
                if e.retryable or e.status == 404:
                    self.mark_unhealthy(model, 3600 if e.status == 404 else None)
                    if not last:
                        log.warning("model %s failed (%s); trying %s", model, str(e)[:120], candidates[i + 1])
                        continue
                raise
            return result, model
        raise LLMError("no model configured", retryable=False)  # pragma: no cover - list is never empty

    async def structured(self, schema: type[T], **kwargs) -> T:
        return (await self.structured_with_meta(schema, **kwargs))[0]

    async def structured_with_meta(
        self,
        schema: type[T],
        *,
        tier: Tier,
        system: str,
        messages: list[ChatMessage] | str,
        ctx: RunContext | None = None,
        purpose: str = "",
        trace: bool = True,
        max_tokens: int = 8000,
    ) -> tuple[T, CallMeta]:
        model = self.model_for(tier)
        msgs = [ChatMessage(role="user", content=messages)] if isinstance(messages, str) else list(messages)
        json_schema = schema.model_json_schema()
        tokens_in = tokens_out = 0
        t0 = time.monotonic()
        last_error = "no attempt made"
        for _attempt in range(2):
            if ctx is not None:
                ctx.check(llm=True)
            try:
                result, model = await self._generate(
                    tier, system=system, messages=msgs, json_schema=json_schema,
                    schema_name=schema.__name__, max_tokens=max_tokens,
                )
            except LLMError as e:
                # Providers already retried transport errors; one more try covers unparseable output.
                if e.retryable and _attempt == 0:
                    last_error = str(e)
                    continue
                raise
            tokens_in += result.usage.input_tokens
            tokens_out += result.usage.output_tokens
            cost = estimate_cost(model, result.usage.input_tokens, result.usage.output_tokens)
            if ctx is not None:
                ctx.usage.llm_calls += 1
                ctx.usage.input_tokens += result.usage.input_tokens
                ctx.usage.output_tokens += result.usage.output_tokens
                ctx.usage.est_cost_usd += cost
            try:
                obj = schema.model_validate(result.data if result.data is not None else {})
            except ValidationError as e:
                last_error = "; ".join(
                    f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}" for err in e.errors()[:8]
                )
                previous = result.text or (json.dumps(result.data) if result.data is not None else "") or "{}"
                msgs = msgs + [
                    ChatMessage(role="assistant", content=previous[:6000]),
                    ChatMessage(role="user", content=f"That JSON did not match the required schema ({last_error}). "
                                                     "Reply with corrected JSON only."),
                ]
                continue
            meta = CallMeta(model=model, input_tokens=tokens_in, output_tokens=tokens_out,
                            latency_ms=int((time.monotonic() - t0) * 1000),
                            cost_usd=estimate_cost(model, tokens_in, tokens_out))
            if ctx is not None and trace:
                await ctx.step("llm_call", purpose or schema.__name__, name=model,
                               output=obj.model_dump(mode="json"), tokens_in=tokens_in, tokens_out=tokens_out,
                               latency_ms=meta.latency_ms)
            return obj, meta
        raise ModelOutputError(f"{purpose or schema.__name__}: output did not match schema after repair ({last_error})")
