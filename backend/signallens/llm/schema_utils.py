"""JSON-schema helpers for provider structured-output features.

Pydantic's ``model_json_schema()`` emits nested models as ``$ref`` pointers into ``$defs``.
Not every provider accepts that (and some reject keywords such as ``title`` or
``default``), so schemas are flattened with :func:`inline_refs` and cleaned with
:func:`strip_keys` before they are sent.

Both functions are schema-aware: keys inside ``properties`` (and similar maps) are field
*names*, not keywords, so a model field called ``title`` survives
``strip_keys(schema, {"title"})``; and ``enum`` / ``const`` / ``default`` / ``examples``
values are data, never walked as schemas. Inputs are never mutated.
"""

from __future__ import annotations

import copy
import logging
import re
from collections.abc import Iterable
from typing import Any
from urllib.parse import unquote

__all__ = ["inline_refs", "safe_schema_name", "strip_keys"]

logger = logging.getLogger(__name__)

# Keywords whose value maps *names* to sub-schemas.
_NAME_MAPS = frozenset({"properties", "patternProperties", "$defs", "definitions", "dependentSchemas"})
# Keywords whose value is literal data, not a schema.
_DATA_KEYS = frozenset({"enum", "const", "default", "examples", "example"})
_DEF_KEYS = frozenset({"$defs", "definitions"})


def inline_refs(schema: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of ``schema`` with local ``$ref`` pointers expanded and ``$defs`` dropped.

    Sibling keywords next to a ``$ref`` (e.g. a field ``description``) are kept and win
    over the referenced definition. A reference that recurses into itself is expanded
    once and then replaced by ``{}`` (any value), since a finite schema cannot express
    unbounded recursion. Non-local references (other documents) are left untouched.
    """
    root = schema

    def resolve(ref: str) -> Any:
        node: Any = root
        for raw in ref[1:].split("/")[1:]:
            key = unquote(raw).replace("~1", "/").replace("~0", "~")
            if isinstance(node, list):
                node = node[int(key)]
            else:
                node = node[key]
        return node

    def walk(node: Any, active: tuple[str, ...]) -> Any:
        if isinstance(node, list):
            return [walk(item, active) for item in node]
        if not isinstance(node, dict):
            return node
        ref = node.get("$ref")
        if isinstance(ref, str) and ref.startswith("#"):
            siblings = {
                k: walk_value(k, v, active) for k, v in node.items() if k != "$ref" and k not in _DEF_KEYS
            }
            if ref in active:
                logger.debug("recursive $ref %s replaced by an unconstrained schema", ref)
                return siblings
            try:
                target = resolve(ref)
            except (KeyError, IndexError, ValueError, TypeError):
                logger.warning("unresolvable $ref %s left in place", ref)
                return {"$ref": ref, **siblings}
            expanded = walk(target, (*active, ref))
            if isinstance(expanded, dict):
                return {**expanded, **siblings}
            return expanded
        return {k: walk_value(k, v, active) for k, v in node.items() if k not in _DEF_KEYS}

    def walk_value(key: str, value: Any, active: tuple[str, ...]) -> Any:
        if key in _DATA_KEYS:
            return copy.deepcopy(value)
        if key in _NAME_MAPS and isinstance(value, dict):
            return {name: walk(sub, active) for name, sub in value.items()}
        return walk(value, active)

    result = walk(schema, ("#",))
    return result if isinstance(result, dict) else {}


def strip_keys(schema: dict[str, Any], keys: Iterable[str]) -> dict[str, Any]:
    """Return a copy of ``schema`` without the given keywords anywhere in the tree.

    Field names inside ``properties`` are never removed, and data values (``enum``,
    ``const``...) are copied verbatim.
    """
    drop = frozenset(keys)

    def walk(node: Any) -> Any:
        if isinstance(node, list):
            return [walk(item) for item in node]
        if not isinstance(node, dict):
            return node
        out: dict[str, Any] = {}
        for key, value in node.items():
            if key in drop:
                continue
            if key in _DATA_KEYS:
                out[key] = copy.deepcopy(value)
            elif key in _NAME_MAPS and isinstance(value, dict):
                out[key] = {name: walk(sub) for name, sub in value.items()}
            else:
                out[key] = walk(value)
        return out

    result = walk(schema)
    return result if isinstance(result, dict) else {}


def safe_schema_name(name: str) -> str:
    """A tool / response-format name every provider accepts (``[A-Za-z0-9_-]{1,64}``)."""
    cleaned = re.sub(r"[^A-Za-z0-9_-]", "_", name.strip())[:64]
    return cleaned or "output"
