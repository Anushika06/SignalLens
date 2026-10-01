from pydantic import BaseModel

from signallens.llm.base import LLMError, LLMResult, LLMUsage
from signallens.runtime.gateway import ModelGateway


class Out(BaseModel):
    answer: str


class FlakyProvider:
    """Fails for the models in `down`; answers for every other model."""

    def __init__(self, down: dict[str, LLMError]):
        self.down = down
        self.calls: list[str] = []

    async def generate(self, *, model, thinking=None, **kwargs):
        self.calls.append(model)
        if model in self.down:
            raise self.down[model]
        return LLMResult(text='{"answer": "ok"}', data={"answer": "ok"}, usage=LLMUsage(1, 1), model=model,
                         provider="fake", latency_ms=1)


def _gateway(provider):
    return ModelGateway(provider, provider_name="nvidia", fast_model="a", reasoning_model="a",
                        fallback_models=("b", "c"))


async def test_stalled_model_fails_over_and_is_skipped_while_cooling_down():
    provider = FlakyProvider({"a": LLMError("timed out", retryable=True)})
    gw = _gateway(provider)
    out, meta = await gw.structured_with_meta(Out, tier="fast", system="", messages="q")
    assert out.answer == "ok" and meta.model == "b"
    assert provider.calls == ["a", "b"]
    await gw.structured(Out, tier="reasoning", system="", messages="q")
    assert provider.calls[-1] == "b" and provider.calls.count("a") == 1  # "a" is cooling down
    assert gw.candidates_for("fast") == ["b", "c", "a"]


async def test_withdrawn_model_fails_over_but_bad_requests_do_not():
    provider = FlakyProvider({"a": LLMError("not found", retryable=False, status=404)})
    out = await _gateway(provider).structured(Out, tier="fast", system="", messages="q")
    assert out.answer == "ok" and provider.calls == ["a", "b"]

    provider = FlakyProvider({"a": LLMError("bad request", retryable=False, status=400)})
    try:
        await _gateway(provider).structured(Out, tier="fast", system="", messages="q")
    except LLMError as e:
        assert e.status == 400
    else:
        raise AssertionError("a 400 must not be retried on another model")
    assert provider.calls == ["a"]
