import pytest

from signallens.llm.base import LLMError, parse_json_object


@pytest.mark.parametrize(
    "text",
    [
        '{"material": true, "score": 2}',
        '```json\n{"material": true, "score": 2}\n```',
        '```\n{"material": true, "score": 2}\n```',
        'Sure! Here is the result:\n{"material": true, "score": 2}\nLet me know if you need more.',
        'Result: {"material": true, "score": 2} {"second": 1}',
    ],
)
def test_parse_json_object_tolerates_fences_and_prose(text):
    assert parse_json_object(text) == {"material": True, "score": 2}


def test_parse_json_object_handles_braces_inside_strings_and_nesting():
    text = 'Answer: {"quote": "use {curly} braces", "nested": {"a": [1, {"b": 2}]}} trailing'
    assert parse_json_object(text) == {"quote": "use {curly} braces", "nested": {"a": [1, {"b": 2}]}}


@pytest.mark.parametrize("text", ["", "no json here", "[1, 2, 3]", '{"unterminated": ', "{not json}"])
def test_parse_json_object_returns_none_when_no_object(text):
    assert parse_json_object(text) is None


def test_llm_error_attributes():
    err = LLMError("boom", retryable=True, status=503)
    assert err.retryable and err.status == 503 and str(err) == "boom"
    assert LLMError("x").retryable is False
