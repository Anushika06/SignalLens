import json

import httpx
import pytest
import respx
from pydantic import BaseModel

from signallens.llm import ChatMessage, GeminiProvider, LLMError

URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"
KEY = "AIza-test-key-0000"


class Inner(BaseModel):
    title: str


class Out(BaseModel):
    verdict: str
    inner: Inner | None = None


def _ok(text, *, finish="STOP", thoughts=None):
    parts = [{"text": "thinking...", "thought": True}] if thoughts else []
    parts.append({"text": text})
    usage = {"promptTokenCount": 40, "candidatesTokenCount": 9}
    if thoughts:
        usage["thoughtsTokenCount"] = thoughts
    return httpx.Response(
        200,
        json={
            "candidates": [{"content": {"role": "model", "parts": parts}, "finishReason": finish}],
            "usageMetadata": usage,
            "modelVersion": "gemini-2.5-flash",
        },
    )


@respx.mock
async def test_request_shape_with_schema():
    route = respx.post(URL).mock(return_value=_ok('{"verdict": "material"}', thoughts=11))
    result = await GeminiProvider(KEY).generate(
        model="gemini-2.5-flash",
        system="Classify.",
        messages=[ChatMessage("user", "Q"), ChatMessage("assistant", "A"), ChatMessage("user", "Q2")],
        json_schema=Out.model_json_schema(),
        max_tokens=512,
        temperature=0.1,
    )
    assert result.data == {"verdict": "material"}
    assert result.text == '{"verdict": "material"}'  # thought parts are not part of the answer
    assert (result.usage.input_tokens, result.usage.output_tokens) == (40, 20)
    assert result.stop_reason == "STOP" and result.model == "gemini-2.5-flash"

    request = route.calls.last.request
    assert request.headers["x-goog-api-key"] == KEY
    body = json.loads(request.content)
    assert body["systemInstruction"] == {"parts": [{"text": "Classify."}]}
    assert [c["role"] for c in body["contents"]] == ["user", "model", "user"]
    config = body["generationConfig"]
    assert config["maxOutputTokens"] == 512 and config["temperature"] == 0.1
    assert config["responseMimeType"] == "application/json"
    schema = config["responseJsonSchema"]
    dumped = json.dumps(schema)
    assert "$ref" not in dumped and "$defs" not in dumped and '"default"' not in dumped
    assert "title" not in schema  # keyword stripped...
    inner = next(opt for opt in schema["properties"]["inner"]["anyOf"] if "properties" in opt)
    assert "title" in inner["properties"]  # ...but the field named "title" survives


@respx.mock
async def test_schema_rejected_with_400_falls_back_to_schema_in_prompt(no_sleep):
    route = respx.post(URL).mock(
        side_effect=[
            httpx.Response(
                400,
                json={
                    "error": {
                        "code": 400,
                        "message": "Invalid JSON payload received. Unknown name \"responseJsonSchema\" at 'generation_config'",
                        "status": "INVALID_ARGUMENT",
                    }
                },
            ),
            _ok('```json\n{"verdict": "noise"}\n```'),
        ]
    )
    result = await GeminiProvider(KEY).generate(
        model="gemini-2.5-flash",
        system="Classify.",
        messages=[ChatMessage("user", "Q")],
        json_schema=Out.model_json_schema(),
    )
    assert result.data == {"verdict": "noise"}
    assert route.call_count == 2
    first = json.loads(route.calls[0].request.content)
    second = json.loads(route.calls[1].request.content)
    assert "responseJsonSchema" in first["generationConfig"]
    assert "responseJsonSchema" not in second["generationConfig"]
    assert second["generationConfig"]["responseMimeType"] == "application/json"
    instruction = second["systemInstruction"]["parts"][0]["text"]
    assert instruction.startswith("Classify.") and '"verdict"' in instruction
    assert no_sleep == []


@respx.mock
async def test_other_400_is_raised_without_fallback():
    route = respx.post(URL).mock(
        return_value=httpx.Response(
            400, json={"error": {"code": 400, "message": "API key not valid.", "status": "INVALID_ARGUMENT"}}
        )
    )
    with pytest.raises(LLMError) as info:
        await GeminiProvider(KEY).generate(
            model="gemini-2.5-flash",
            system="s",
            messages=[ChatMessage("user", "Q")],
            json_schema=Out.model_json_schema(),
        )
    assert not info.value.retryable and route.call_count == 1


@respx.mock
async def test_blocked_prompt_raises_non_retryable():
    respx.post(URL).mock(return_value=httpx.Response(200, json={"promptFeedback": {"blockReason": "SAFETY"}}))
    with pytest.raises(LLMError) as info:
        await GeminiProvider(KEY).generate(
            model="gemini-2.5-flash", system="s", messages=[ChatMessage("user", "Q")]
        )
    assert info.value.retryable is False


@respx.mock
async def test_plain_text_and_model_prefix(no_sleep):
    route = respx.post(URL).mock(
        side_effect=[httpx.Response(500, json={"error": {"message": "internal"}}), _ok("Hello")]
    )
    result = await GeminiProvider(KEY).generate(
        model="models/gemini-2.5-flash", system="", messages=[ChatMessage("user", "hi")]
    )
    assert result.text == "Hello" and result.data is None
    body = json.loads(route.calls.last.request.content)
    assert "systemInstruction" not in body and "responseMimeType" not in body["generationConfig"]
    assert no_sleep == [1.0]
