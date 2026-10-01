import pytest

from signallens.llm import ChatMessage, LLMError, LLMResult, LLMUsage, ScriptedLLM, ScriptExhaustedError

SCHEMA = {"type": "object", "properties": {"material": {"type": "boolean"}}}


async def test_scripted_responses_in_order_and_calls_recorded():
    llm = ScriptedLLM([{"material": True}, "plain text"])
    first = await llm.generate(
        model="fast",
        system="sys",
        messages=[ChatMessage("user", "hello")],
        json_schema=SCHEMA,
        schema_name="triage",
    )
    second = await llm.generate(model="fast", system="sys", messages=[ChatMessage("user", "again")])
    assert first.data == {"material": True} and first.text == '{"material": true}'
    assert second.text == "plain text" and second.data is None
    assert first.provider == "scripted" and first.model == "fast"
    assert first.usage.input_tokens > 0 and first.usage.output_tokens > 0
    assert len(llm.calls) == 2
    assert llm.calls[0]["schema_name"] == "triage"
    assert llm.calls[0]["json_schema"] is SCHEMA
    assert llm.calls[1]["messages"][0].content == "again"
    assert llm.last_call is llm.calls[1]
    assert llm.remaining == 0


async def test_exhausted_script_fails_loudly():
    llm = ScriptedLLM(["only one"])
    await llm.generate(model="m", system="s", messages=[ChatMessage("user", "1")])
    with pytest.raises(ScriptExhaustedError, match="1 response"):
        await llm.generate(model="m", system="s", messages=[ChatMessage("user", "2")], schema_name="impact")


async def test_string_with_schema_is_parsed_like_model_output():
    llm = ScriptedLLM(['```json\n{"material": false}\n```', "not json"])
    result = await llm.generate(model="m", system="s", messages=[], json_schema=SCHEMA)
    assert result.data == {"material": False}
    with pytest.raises(LLMError) as info:
        await llm.generate(model="m", system="s", messages=[], json_schema=SCHEMA)
    assert info.value.retryable


async def test_exceptions_and_results_in_script():
    canned = LLMResult(text="x", data=None, usage=LLMUsage(1, 1), model="m", provider="p", latency_ms=5)
    llm = ScriptedLLM([LLMError("rate limited", retryable=True), canned])
    with pytest.raises(LLMError, match="rate limited"):
        await llm.generate(model="m", system="s", messages=[])
    assert await llm.generate(model="m", system="s", messages=[]) is canned


async def test_returned_data_is_a_copy():
    scripted = {"items": [1]}
    llm = ScriptedLLM([scripted])
    result = await llm.generate(model="m", system="s", messages=[], json_schema=SCHEMA)
    result.data["items"].append(2)
    assert scripted == {"items": [1]}


async def test_sync_and_async_handlers():
    def handler(system, messages, json_schema, schema_name):
        return {"schema": schema_name} if json_schema else f"echo: {messages[-1].content}"

    llm = ScriptedLLM(handler)
    assert (
        await llm.generate(model="m", system="s", messages=[ChatMessage("user", "hi")])
    ).text == "echo: hi"
    assert (
        await llm.generate(model="m", system="s", messages=[], json_schema=SCHEMA, schema_name="x")
    ).data == {"schema": "x"}
    assert llm.remaining is None

    async def async_handler(system, messages, json_schema, schema_name):
        return "async ok"

    assert (await ScriptedLLM(async_handler).generate(model="m", system="s", messages=[])).text == "async ok"


def test_rejects_invalid_scripts():
    with pytest.raises(TypeError):
        ScriptedLLM("not a list")  # type: ignore[arg-type]


async def test_context_manager_closes():
    async with ScriptedLLM([]) as llm:
        pass
    assert llm.closed
