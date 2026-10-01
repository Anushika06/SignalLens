from __future__ import annotations

import json

from pydantic import BaseModel, Field

from signallens.llm.schema_utils import inline_refs, safe_schema_name, strip_keys


class Evidence(BaseModel):
    quote: str
    url: str
    stance: str = Field(default="supports", description="supports / contradicts / context")


class Claim(BaseModel):
    title: str  # a *field* called "title" must survive strip_keys(..., {"title"})
    evidence: list[Evidence]
    primary: Evidence | None = None
    status: str = Field(default="unverified", examples=["confirmed"])


class Node(BaseModel):
    name: str
    children: list[Node] = []


def _has_key(node, key):
    if isinstance(node, dict):
        return key in node or any(_has_key(v, key) for v in node.values())
    if isinstance(node, list):
        return any(_has_key(v, key) for v in node)
    return False


def test_inline_refs_resolves_nested_models_and_optional():
    schema = Claim.model_json_schema()
    assert "$defs" in schema
    inlined = inline_refs(schema)
    assert not _has_key(inlined, "$ref")
    assert not _has_key(inlined, "$defs")
    items = inlined["properties"]["evidence"]["items"]
    assert items["properties"]["quote"]["type"] == "string"
    primary = inlined["properties"]["primary"]
    assert any(opt.get("type") == "null" for opt in primary["anyOf"])
    assert any("properties" in opt for opt in primary["anyOf"])


def test_inline_refs_does_not_mutate_input():
    schema = Claim.model_json_schema()
    before = json.dumps(schema, sort_keys=True)
    inline_refs(schema)
    assert json.dumps(schema, sort_keys=True) == before


def test_inline_refs_keeps_sibling_keywords_next_to_ref():
    schema = {
        "type": "object",
        "properties": {"ev": {"$ref": "#/$defs/E", "description": "the evidence"}},
        "$defs": {"E": {"type": "object", "description": "generic", "properties": {"q": {"type": "string"}}}},
    }
    out = inline_refs(schema)
    assert out["properties"]["ev"]["description"] == "the evidence"
    assert out["properties"]["ev"]["properties"]["q"] == {"type": "string"}


class Tree(BaseModel):
    root: Node


def test_inline_refs_guards_recursion():
    # A self-referencing root model: the root is the one expanded level.
    inlined = inline_refs(Node.model_json_schema())
    assert not _has_key(inlined, "$ref") and not _has_key(inlined, "$defs")
    assert inlined["properties"]["name"]["type"] == "string"
    assert inlined["properties"]["children"]["items"] == {}

    # A recursive model nested inside another: expanded once, then cut.
    tree = inline_refs(Tree.model_json_schema())
    assert not _has_key(tree, "$ref") and not _has_key(tree, "$defs")
    node = tree["properties"]["root"]
    assert node["properties"]["name"]["type"] == "string"
    assert node["properties"]["children"]["items"] == {}


def test_inline_refs_supports_legacy_definitions():
    schema = {"properties": {"a": {"$ref": "#/definitions/A"}}, "definitions": {"A": {"type": "integer"}}}
    assert inline_refs(schema) == {"properties": {"a": {"type": "integer"}}}


def test_strip_keys_removes_keywords_but_not_field_names():
    stripped = strip_keys(inline_refs(Claim.model_json_schema()), {"title", "default", "examples"})
    assert "title" in stripped["properties"]  # the field survives
    assert "title" not in stripped["properties"]["title"]  # its keyword is gone
    assert not _has_key({k: v for k, v in stripped.items() if k != "properties"}, "title")
    assert "default" not in stripped["properties"]["status"]
    assert "examples" not in stripped["properties"]["status"]
    assert stripped["required"] == ["title", "evidence"]


def test_strip_keys_leaves_enum_data_alone():
    schema = {"type": "string", "enum": [{"title": "x"}], "title": "T"}
    assert strip_keys(schema, {"title"}) == {"type": "string", "enum": [{"title": "x"}]}


def test_safe_schema_name():
    assert safe_schema_name("triage") == "triage"
    assert safe_schema_name("impact analysis/v2") == "impact_analysis_v2"
    assert safe_schema_name("") == "output"
    assert len(safe_schema_name("x" * 100)) == 64
