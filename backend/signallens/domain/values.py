"""Comparing tracked attribute values without being fooled by phrasing.

Models describe the same value in different words ("2% per transaction" vs "2 % flat").
Numeric attributes compare on number + unit (+ conditions); text attributes compare on
normalised text, and the extractor is told the previous value and asked whether it is
unchanged, so rephrasing alone never creates an event.
"""

from __future__ import annotations

import hashlib

from rapidfuzz import fuzz

from signallens.util.text import normalize_for_match

UNIT_ALIASES = {
    "percent": "%", "pct": "%", "per cent": "%", "%": "%",
    "inr": "INR", "rs": "INR", "rs.": "INR", "₹": "INR", "rupees": "INR",
    "usd": "USD", "$": "USD", "us$": "USD", "eur": "EUR", "€": "EUR", "gbp": "GBP", "£": "GBP",
}


def norm_unit(unit: str | None) -> str:
    if not unit:
        return ""
    u = unit.strip().lower()
    return UNIT_ALIASES.get(u, u.upper() if len(u) <= 4 else u)


def value_key(*, display: str, number: float | None, unit: str | None, conditions: str | None) -> str:
    if number is not None:
        basis = f"n:{round(float(number), 4)}|u:{norm_unit(unit)}|c:{normalize_for_match(conditions or '')}"
    else:
        basis = f"t:{normalize_for_match(display)}"
    return hashlib.sha256(basis.encode()).hexdigest()[:32]


def equivalent(
    prev: dict, *, display: str, number: float | None, unit: str | None, conditions: str | None,
    same_as_previous: bool | None = None,
) -> bool:
    """True if the new reading describes the same value as ``prev`` (a StateVersion.value dict)."""
    if same_as_previous is True:
        return True
    p_num, p_unit = prev.get("number"), norm_unit(prev.get("unit"))
    if number is not None and p_num is not None:
        if round(float(number), 4) != round(float(p_num), 4) or norm_unit(unit) != p_unit:
            return False
        a, b = normalize_for_match(conditions or ""), normalize_for_match(prev.get("conditions") or "")
        return a == b or (bool(a) and bool(b) and fuzz.token_set_ratio(a, b) >= 85)
    a, b = normalize_for_match(display), normalize_for_match(prev.get("display") or "")
    return a == b or fuzz.token_set_ratio(a, b) >= 95
