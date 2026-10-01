import json

import httpx
import pytest
import respx
from pydantic import BaseModel

from signallens.llm import ChatMessage, LLMError, OpenAIProvider, is_reasoning_model

URL = "https://api.openai.com/v1/chat/completions"


class Out(BaseModel):
    answer: str


def _ok(content, *, finish_reason="stop", refusal=None):
    return httpx.Response(
        200,
        json={
            "id": "chatcmpl-1",
            "model": "gpt-4.1-mini-2025-04-14",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": content, "refusal": refusal},
                    "finish_reason": finish_reason,
                }
            ],
            "usage": {"prompt_tokens": 50, "completion_tokens": 7, "total_tokens": 57},
        },
    )


@respx.mock
async def test_request_shape_and_structured_output():
    route = respx.post(URL).mock(return_value=_ok('{"answer": "yes"}'))
    llm = OpenAIProvider("sk-test-000000")
    result = await llm.generate(
        model="gpt-4.1-mini",
        system="Be brief.",
        messages=[ChatMessage("user", "Q1"), ChatMessage("assistant", "A1"), ChatMessage("user", "Q2")],
        json_schema=Out.model_json_schema(),
        schema_name="answer",
        max_tokens=256,
        temperature=0.2,
    )
    assert result.data == {"answer": "yes"}
    assert (result.usage.input_tokens, result.usage.output_tokens) == (50, 7)
    assert result.provider == "openai" and result.stop_reason == "stop"

    request = route.calls.last.request
    assert request.headers["authorization"] == "Bearer sk-test-000000"
    body = json.loads(request.content)
    assert body["messages"][0] == {"role": "system", "content": "Be brief."}
    assert [m["role"] for m in body["messages"]] == ["system", "user", "assistant", "user"]
    assert body["max_completion_tokens"] == 256
    assert body["temperature"] == 0.2
    fmt = body["response_format"]
    assert fmt["type"] == "json_schema"
    assert fmt["json_schema"]["name"] == "answer" and fmt["json_schema"]["strict"] is False
    assert fmt["json_schema"]["schema"]["properties"]["answer"]["type"] == "string"


@pytest.mark.parametrize(
    "model", ["gpt-5", "gpt-5-mini", "o1-preview", "o3-mini", "o4-mini", "openai/gpt-5-nano"]
)
def test_reasoning_models_are_detected(model):
    assert is_reasoning_model(model)


@pytest.mark.parametrize("model", ["gpt-4.1", "gpt-4o-mini", "llama3.1:8b", "qwen2.5"])
def test_non_reasoning_models(model):
    assert not is_reasoning_model(model)


@respx.mock
async def test_temperature_not_sent_to_reasoning_models():
    respx.post(URL).mock(return_value=_ok("hi"))
    await OpenAIProvider("k").generate(
        model="gpt-5-mini", system="s", messages=[ChatMessage("user", "u")], temperature=0.3
    )
    assert "temperature" not in json.loads(respx.calls.last.request.content)


@respx.mock
async def test_json_in_fences_and_prose_is_parsed():
    respx.post(URL).mock(return_value=_ok('Here you go:\n```json\n{"answer": "fenced"}\n```\nAnything else?'))
    result = await OpenAIProvider("k").generate(
        model="gpt-4.1", system="s", messages=[ChatMessage("user", "u")], json_schema=Out.model_json_schema()
    )
    assert result.data == {"answer": "fenced"}


@respx.mock
async def test_unparseable_json_is_retryable():
    respx.post(URL).mock(return_value=_ok("I think the answer is yes", finish_reason="length"))
    with pytest.raises(LLMError) as info:
        await OpenAIProvider("k").generate(
            model="gpt-4.1",
            system="s",
            messages=[ChatMessage("user", "u")],
            json_schema=Out.model_json_schema(),
        )
    assert info.value.retryable is True
    assert "I think the answer" in str(info.value)


@respx.mock
async def test_refusal_is_not_retryable():
    respx.post(URL).mock(return_value=_ok(None, refusal="I can't help with that."))
    with pytest.raises(LLMError) as info:
        await OpenAIProvider("k").generate(model="gpt-4.1", system="s", messages=[ChatMessage("user", "u")])
    assert info.value.retryable is False


@respx.mock
async def test_ollama_compatible_base_url_without_key():
    route = respx.post("http://localhost:11434/v1/chat/completions").mock(
        return_value=_ok('{"answer": "local"}')
    )
    llm = OpenAIProvider("", base_url="http://localhost:11434/v1")
    result = await llm.generate(
        model="llama3.1:8b",
        system="s",
        messages=[ChatMessage("user", "u")],
        json_schema=Out.model_json_schema(),
        temperature=0,
    )
    assert result.data == {"answer": "local"}
    request = route.calls.last.request
    assert "authorization" not in request.headers
    assert json.loads(request.content)["temperature"] == 0


@respx.mock
async def test_429_then_success(no_sleep):
    route = respx.post(URL).mock(
        side_effect=[
            httpx.Response(429, headers={"retry-after-ms": "1500"}, json={"error": {"message": "slow down"}}),
            _ok("ok"),
        ]
    )
    result = await OpenAIProvider("k").generate(
        model="gpt-4.1", system="s", messages=[ChatMessage("user", "u")]
    )
    assert result.text == "ok" and route.call_count == 2
    assert no_sleep == [1.5]


@respx.mock
async def test_401_is_not_retried(no_sleep):
    route = respx.post(URL).mock(
        return_value=httpx.Response(
            401, json={"error": {"message": "Incorrect API key provided", "type": "invalid_request_error"}}
        )
    )
    with pytest.raises(LLMError) as info:
        await OpenAIProvider("k").generate(model="gpt-4.1", system="s", messages=[ChatMessage("user", "u")])
    assert info.value.status == 401 and not info.value.retryable
    assert "Incorrect API key provided" in str(info.value)
    assert route.call_count == 1
