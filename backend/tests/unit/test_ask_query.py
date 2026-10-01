"""Ask: full-text query building, LIKE escaping, citation markers and citation ids."""

from __future__ import annotations

from signallens.agents.ask import Citation, normalize_citation, renumber_markers
from signallens.tools.memory import build_tsquery, like_patterns, search_terms


def test_search_terms_drop_question_filler():
    assert search_terms("What has Razorpay changed in pricing this year?") == ["razorpay", "pricing"]
    assert search_terms("What should Compliance look at this week?") == ["compliance"]
    assert search_terms("Which competitor announced partnerships recently and is it confirmed?") == [
        "competitor", "announced", "partnerships", "confirmed"]


def test_search_terms_keep_names_codes_and_numbers():
    assert search_terms("Razorpay's UPI fee vs Cashfree's 1.9% fee") == ["razorpay", "upi", "fee", "vs", "cashfree", "1.9"]
    assert search_terms("pricing.standard_domestic_fee") == ["pricing.standard_domestic_fee"]
    assert search_terms("AT&T e-mandate") == ["at&t", "e-mandate"]
    assert search_terms("a I the") == []


def test_build_tsquery_ors_terms_and_keeps_phrases():
    assert build_tsquery("What has Razorpay changed in pricing this year?") == "razorpay or pricing"
    assert build_tsquery('Compare "Cashfree Payments" and Razorpay fees') == '"cashfree payments" or compare or razorpay or fees'
    assert build_tsquery("what is this?") is None
    assert build_tsquery("") is None


def test_build_tsquery_never_emits_negation_or_operators():
    q = build_tsquery("-razorpay --fees OR 'x' <script>")
    assert q is not None
    assert not any(part.startswith("-") for part in q.split(" or "))
    assert "<" not in q and "'" not in q


def test_build_tsquery_caps_terms():
    q = build_tsquery(" ".join(f"term{i}" for i in range(40)))
    assert q is not None and len(q.split(" or ")) == 12


def test_like_patterns_escape_wildcards():
    assert like_patterns("100% fee_cap") == ["%100%", r"%fee\_cap%"]
    assert like_patterns("%_") == [r"%\%\_%"]  # no words: the raw text, escaped
    assert like_patterns("the") == ["%the%"]  # only filler: search the raw text
    assert like_patterns("   ") == []


def test_renumber_markers_after_drops_and_merges():
    md = "Fee cut to 1.8% [1][2]. Other claim [3]. Both [1, 3]. Link [1](https://x.example)."
    assert renumber_markers(md, {1: 1, 2: 2}) == "Fee cut to 1.8% [1][2]. Other claim. Both [1]. Link [1](https://x.example)."
    # Duplicate citations collapse onto one position.
    assert renumber_markers("A [1] B [2] C [1,2]", {1: 1, 2: 1}) == "A [1] B [1] C [1]"
    assert renumber_markers("No markers here.", {}) == "No markers here."


def test_normalize_citation_ids():
    c = normalize_citation(Citation(kind="fact", id=" [fact:ABCDEF00-0000-0000-0000-000000000000] ", label=" Fee "))
    assert c.id == "abcdef00-0000-0000-0000-000000000000" and c.label == "Fee"
    web = normalize_citation(Citation(kind="web", id="web:https://Example.com/A"))
    assert web.id == "https://Example.com/A"
