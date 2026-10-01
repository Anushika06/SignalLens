"""Make arbitrary values safe to store in JSONB run traces (and small enough to read)."""

from __future__ import annotations

import dataclasses
import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel


def jsonable(value: Any, *, max_str: int = 4000, max_items: int = 50, _depth: int = 0) -> Any:
    if _depth > 8:
        return "…"
    if value is None or isinstance(value, bool | int | float):
        return value
    if isinstance(value, str):
        return value if len(value) <= max_str else value[:max_str] + f"… [+{len(value) - max_str} chars]"
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    elif dataclasses.is_dataclass(value) and not isinstance(value, type):
        value = dataclasses.asdict(value)
    if isinstance(value, dict):
        items = list(value.items())
        out = {str(k): jsonable(v, max_str=max_str, max_items=max_items, _depth=_depth + 1) for k, v in items[:max_items]}
        if len(items) > max_items:
            out["…"] = f"{len(items) - max_items} more keys"
        return out
    if isinstance(value, list | tuple | set):
        seq = list(value)
        out_list = [jsonable(v, max_str=max_str, max_items=max_items, _depth=_depth + 1) for v in seq[:max_items]]
        if len(seq) > max_items:
            out_list.append(f"… {len(seq) - max_items} more")
        return out_list
    if isinstance(value, bytes):
        return f"<{len(value)} bytes>"
    return str(value)[:max_str]
