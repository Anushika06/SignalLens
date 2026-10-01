import json

import httpx
import pytest
import respx
from pydantic import BaseModel

from signallens.llm import AnthropicProvider, ChatMessage, LLMError

URL = "https://api.anthropic.com/v1/messages"
KEY = "sk-ant-secret-key-123456"


class Sub(BaseModel):
    note: str


class Triage(BaseModel):
    material: bool
    reason: str
    sub: Sub | None = None


def _ok(content, *, stop_reason="end_turn", model="claude-sonnet-4-5-20250929"):
    return httpx.Response(
        200,
        json={
            "id": "msg_1",
            "type": "message",
            "role": "assistant",
            "model": model,
            "content": content,
            "stop_reason": stop_reason,
            "usage": {"input_tokens": 120, "output_tokens": 30},
        },
    )


@respx.mock
async def test_structured_output_via_forced_tool_use():
    route = respx.post(URL).mock(
        return_value=_ok(
            [
                {"type": "text", "text": "Classifying."},
                {
                    "type": "tool_use",
                    "id": "toolu_1",
                    "name": "triage",
                    "input": {"material": True, "reason": "fee cut"},
                },
            ],
            stop_reason="tool_use",
        )
    )
    llm = AnthropicProvider(KEY)
    result = await llm.generate(
        model="claude-sonnet-4-5",
        system="You classify changes.",
        messages=[ChatMessage("user", "Fee changed from 2% to 1.8%")],
        json_schema=Triage.model_json_schema(),
        schema_name="triage",
        temperature=0.0,
    )
    await llm.aclose()

    assert result.data == {"material": True, "reason": "fee cut"}
    assert json.loads(result.text) == result.data
    assert result.provider == "anthropic"
    assert result.model == "claude-sonnet-4-5-20250929"
    assert result.stop_reason == "tool_use"
    assert (result.usage.input_tokens, result.usage.output_tokens) == (120, 30)

    request = route.calls.last.request
    assert request.headers["x-api-key"] == KEY
    assert request.headers["anthropic-version"] == "2023-06-01"
    body = json.loads(request.content)
    assert body["system"] == "You classify changes."
    assert body["messages"] == [{"role": "user", "content": "Fee changed from 2% to 1.8%"}]
    assert body["temperature"] == 0.0
    assert body["tool_choice"] == {"type": "tool", "name": "triage"}
    tool = body["tools"][0]
    assert tool["name"] == "triage" and tool["description"] == "Return the result"
    assert "$defs" not in tool["input_schema"] and "$ref" not in json.dumps(tool["input_schema"])


@respx.mock
async def test_plain_text_generation():
    respx.post(URL).mock(return_value=_ok([{"type": "text", "text": "Hello there"}]))
    llm = AnthropicProvider(KEY)
    result = await llm.generate(model="m", system="", messages=[ChatMessage("user", "hi")])
    assert result.text == "Hello there" and result.data is None
    body = json.loads(respx.calls.last.request.content)
    assert "system" not in body and "tools" not in body and "temperature" not in body


@respx.mock
async def test_falls_back_to_json_in_text_when_no_tool_call():
    respx.post(URL).mock(
        return_value=_ok([{"type": "text", "text": '```json\n{"material": false, "reason": "x"}\n```'}])
    )
    result = await AnthropicProvider(KEY).generate(
        model="m", system="s", messages=[ChatMessage("user", "u")], json_schema=Triage.model_json_schema()
    )
    assert result.data == {"material": False, "reason": "x"}


@respx.mock
async def test_unparseable_structured_output_is_retryable_error():
    respx.post(URL).mock(
        return_value=_ok([{"type": "text", "text": "I cannot comply"}], stop_reason="max_tokens")
    )
    with pytest.raises(LLMError) as info:
        await AnthropicProvider(KEY).generate(
            model="m", system="s", messages=[ChatMessage("user", "u")], json_schema=Triage.model_json_schema()
        )
    assert info.value.retryable is True
    assert "max_tokens" in str(info.value)


@respx.mock
async def test_retries_429_then_succeeds_honouring_retry_after(no_sleep):
    route = respx.post(URL).mock(
        side_effect=[
            httpx.Response(429, headers={"retry-after": "7"}, json={"error": {"message": "rate limited"}}),
            httpx.Response(
                529, json={"type": "error", "error": {"type": "overloaded_error", "message": "Overloaded"}}
            ),
            _ok([{"type": "text", "text": "done"}]),
        ]
    )
    result = await AnthropicProvider(KEY).generate(model="m", system="s", messages=[ChatMessage("user", "u")])
    assert result.text == "done"
    assert route.call_count == 3
    assert no_sleep == [7.0, 3.0]


@respx.mock
async def test_retry_after_is_capped(no_sleep):
    respx.post(URL).mock(
        side_effect=[
            httpx.Response(429, headers={"retry-after": "600"}),
            _ok([{"type": "text", "text": "ok"}]),
        ]
    )
    await AnthropicProvider(KEY).generate(model="m", system="s", messages=[ChatMessage("user", "u")])
    assert no_sleep == [20.0]


@respx.mock
async def test_non_retryable_400_carries_provider_message_without_key(no_sleep):
    route = respx.post(URL).mock(
        return_value=httpx.Response(
            400,
            json={
                "type": "error",
                "error": {"type": "invalid_request_error", "message": f"bad key {KEY} used"},
            },
        )
    )
    with pytest.raises(LLMError) as info:
        await AnthropicProvider(KEY).generate(model="m", system="s", messages=[ChatMessage("user", "u")])
    assert info.value.retryable is False and info.value.status == 400
    assert "bad key" in str(info.value)
    assert KEY not in str(info.value)
    assert route.call_count == 1 and no_sleep == []


@respx.mock
async def test_exhausted_retries_raise_retryable_error(no_sleep):
    route = respx.post(URL).mock(return_value=httpx.Response(503, text="upstream unavailable"))
    llm = AnthropicProvider(KEY, max_retries=2)
    with pytest.raises(LLMError) as info:
        await llm.generate(model="m", system="s", messages=[ChatMessage("user", "u")])
    assert info.value.retryable is True and info.value.status == 503
    assert route.call_count == 3
    assert no_sleep == [1.0, 3.0]


@respx.mock
async def test_timeouts_and_connection_errors_are_retried(no_sleep):
    respx.post(URL).mock(
        side_effect=[
            httpx.ConnectTimeout("slow"),
            httpx.ConnectError("refused"),
            _ok([{"type": "text", "text": "ok"}]),
        ]
    )
    result = await AnthropicProvider(KEY).generate(model="m", system="s", messages=[ChatMessage("user", "u")])
    assert result.text == "ok"


@respx.mock
async def test_custom_base_url_and_shared_client():
    route = respx.post("https://proxy.internal.example/v1/messages").mock(
        return_value=_ok([{"type": "text", "text": "x"}])
    )
    async with httpx.AsyncClient() as client:
        llm = AnthropicProvider(KEY, base_url="https://proxy.internal.example/", http=client)
        await llm.generate(model="m", system="s", messages=[ChatMessage("user", "u")])
        await llm.aclose()  # must not close a client it does not own
        assert not client.is_closed
    assert route.called
    assert KEY not in repr(llm)
