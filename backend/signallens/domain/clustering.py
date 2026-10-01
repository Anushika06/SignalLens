"""Event clustering (spec review C3).

Fifteen articles about one funding round must become one event with fifteen pieces of
evidence. Each detected item gets a structured key built from what the event *is*
(type + entity + counterparty/product/person/round); items with the same key, or a
near-identical headline about the same entity and type, attach to the existing event.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime

from rapidfuzz import fuzz

# Legal forms and generic corporate descriptors. Deliberately excludes words that tell
# companies apart (bank, motors, steel, pharma...): "Tata Motors" must not merge with "Tata Steel".
CORPORATE_SUFFIXES = {
    "inc", "ltd", "limited", "pvt", "private", "llc", "llp", "corp", "corporation", "co", "plc", "gmbh",
    "sa", "ag", "bv", "nv", "the", "company", "group", "holdings", "technologies", "technology", "software",
    "solutions", "services", "systems", "labs", "ventures", "global", "international", "india",
}

CLUSTER_WINDOW_DAYS = 21
TITLE_SIMILARITY = 82


def slug(value: str | None, *, max_len: int = 60, strip_suffixes: bool = False) -> str:
    if not value:
        return ""
    text = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().lower()
    words = re.findall(r"[a-z0-9]+", text)
    if strip_suffixes:
        words = [w for w in words if w not in CORPORATE_SUFFIXES] or words
    return "-".join(words)[:max_len].strip("-")


def cluster_key(
    event_type: str,
    entity_key: str,
    *,
    counterparty: str | None = None,
    product: str | None = None,
    person: str | None = None,
    round_or_amount: str | None = None,
    topic: str | None = None,
    when: datetime | None = None,
) -> str:
    """Structured identity of an event. Falls back to type + entity + topic words."""
    entity = slug(entity_key, strip_suffixes=True) or "unknown"
    cp = slug(counterparty, strip_suffixes=True)
    if event_type in ("partnership", "acquisition") and cp:
        return f"{event_type}:{entity}:{cp}"
    if event_type == "funding":
        return f"funding:{entity}:{slug(round_or_amount) or (when.strftime('%Y-%m') if when else 'na')}"
    if event_type == "leadership" and person:
        return f"leadership:{entity}:{slug(person)}"
    if event_type == "product_launch" and product:
        return f"launch:{entity}:{slug(product, strip_suffixes=True)}"
    if event_type == "regulatory":
        return f"regulatory:{entity}:{slug(topic or product, max_len=50)}"
    if event_type == "pricing":
        return f"pricing:{entity}:{slug(product or topic, max_len=40) or 'general'}"
    return f"{event_type}:{entity}:{slug(topic or product or counterparty, max_len=50)}"


def titles_similar(a: str, b: str, threshold: int = TITLE_SIMILARITY) -> bool:
    return fuzz.token_set_ratio(a.lower(), b.lower()) >= threshold
