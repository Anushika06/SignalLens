import json

import httpx
import respx
from pydantic import BaseModel

from signallens.config import Settings
from signallens.llm import ChatMessage, NvidiaProvider, require_all_properties
from signallens.runtime.services import build_gateway

URL = "https://integrate.api.nvidia.com/v1/chat/completions"


class Inner(BaseModel):
    quote: str | None = None


class Out(BaseModel):
    key: str
    value: str | None = None
    items: list[Inner] = []


def test_require_all_properties_marks_every_object_property_required():
    schema = require_all_properties({
        "type": "object",
        "properties": {"a": {"type": "string"}, "b": {"type": "object", "properties": {"c": {"type": "integer"}}}},
        "required": ["a"],
    })
    assert schema["required"] == ["a", "b"]
    assert schema["properties"]["b"]["required"] == ["c"]


@respx.mock
async def test_nim_request_uses_nim_endpoint_and_a_fully_required_schema():
    route = respx.post(URL).mock(return_value=httpx.Response(200, json={
        "model": "nvidia/nemotron-3-super-120b-a12b",
        "choices": [{"message": {"role": "assistant", "content": '{"key": "fee", "value": null, "items": []}'},
                     "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5},
    }))
    llm = NvidiaProvider("nvapi-test-0000")
    result = await llm.generate(model="nvidia/nemotron-3-super-120b-a12b", system="s",
                                messages=[ChatMessage("user", "q")], json_schema=Out.model_json_schema(),
                                schema_name="Out")
    body = json.loads(route.calls.last.request.content)
    schema = body["response_format"]["json_schema"]["schema"]
    assert schema["required"] == ["key", "value", "items"]
    assert schema["properties"]["items"]["items"]["required"] == ["quote"]
    assert route.calls.last.request.headers["authorization"] == "Bearer nvapi-test-0000"
    assert result.provider == "nvidia" and result.data == {"key": "fee", "value": None, "items": []}


def test_auto_provider_is_nvidia_only():
    gw = build_gateway(Settings(_env_file=None, nvidia_api_key="nvapi-x", gemini_api_key="g", openai_api_key="o"))
    assert gw is not None and gw.provider_name == "nvidia"
    assert build_gateway(Settings(_env_file=None, nvidia_api_key=None, gemini_api_key="g")) is None


@respx.mock
async def test_thinking_switch_is_sent_only_when_requested():
    route = respx.post(URL).mock(return_value=httpx.Response(200, json={
        "choices": [{"message": {"content": "hi"}, "finish_reason": "stop"}], "usage": {}}))
    llm = NvidiaProvider("nvapi-test-0000")
    await llm.generate(model="m", system="", messages=[ChatMessage("user", "q")], thinking=False)
    assert json.loads(route.calls.last.request.content)["chat_template_kwargs"] == {"enable_thinking": False}
    await llm.generate(model="m", system="", messages=[ChatMessage("user", "q")])
    assert "chat_template_kwargs" not in json.loads(route.calls.last.request.content)


def test_gateway_thinking_tiers_follow_the_setting():
    off = build_gateway(Settings(_env_file=None, nvidia_api_key="nvapi-x"))
    assert off.thinking_for("fast") is False and off.thinking_for("reasoning") is False
    deep = build_gateway(Settings(_env_file=None, nvidia_api_key="nvapi-x", llm_thinking="reasoning"))
    assert deep.thinking_for("fast") is False and deep.thinking_for("reasoning") is True
