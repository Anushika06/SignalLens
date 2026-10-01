"""Ordered vocabularies shared by the pipeline, the policy engine and the API."""

from __future__ import annotations

MATERIALITY = ("none", "low", "medium", "high", "critical")
SEVERITY = ("low", "medium", "high", "critical")
IMPORTANCE = ("low", "medium", "high", "critical")
EVIDENCE_STATUSES = ("confirmed", "corroborated", "single_source", "conflicting", "unverified")

EVENT_TYPES = (
    "value_change", "item_added", "item_removed", "content_change", "product_launch", "pricing",
    "partnership", "funding", "leadership", "regulatory", "legal", "acquisition", "financials",
    "expansion", "other",
)

CHANGE_LABELS = {
    "value_change": "Value change",
    "item_added": "Something added",
    "item_removed": "Something removed",
    "content_change": "Content change",
    "product_launch": "Product launch",
    "pricing": "Pricing change",
    "partnership": "New partnership",
    "funding": "Funding",
    "leadership": "Leadership change",
    "regulatory": "Regulatory development",
    "legal": "Legal development",
    "acquisition": "Acquisition",
    "financials": "Financial results",
    "expansion": "Expansion",
    "other": "Development",
}

EVIDENCE_LABELS = {
    "confirmed": "Confirmed",
    "corroborated": "Corroborated",
    "single_source": "Single source",
    "conflicting": "Conflicting",
    "unverified": "Unverified",
}


def rank(scale: tuple[str, ...], value: str | None) -> int:
    """Position of ``value`` in ``scale`` (unknown values rank lowest)."""
    try:
        return scale.index(value or "")
    except ValueError:
        return 0


def at_least(scale: tuple[str, ...], value: str | None, threshold: str) -> bool:
    return rank(scale, value) >= rank(scale, threshold)


def step(scale: tuple[str, ...], value: str, delta: int) -> str:
    """Move ``value`` up (+) or down (-) the scale, clamped to its ends."""
    i = max(0, min(len(scale) - 1, rank(scale, value) + delta))
    return scale[i]


def lower_of(scale: tuple[str, ...], a: str, b: str) -> str:
    return a if rank(scale, a) <= rank(scale, b) else b


def coerce(scale: tuple[str, ...], value: str | None, default: str) -> str:
    """Return ``value`` if it belongs to ``scale``, else ``default`` (model outputs vary)."""
    v = (value or "").strip().lower()
    return v if v in scale else default
