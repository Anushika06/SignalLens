"""Deterministic product rules: evidence rubric, policy, severity caps, feedback learning, clustering."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from signallens.domain.clustering import cluster_key, slug, titles_similar
from signallens.domain.evidence import EvidenceItem, assess, classify_source
from signallens.domain.feedback import FeedbackContext, interpret
from signallens.domain.policy import build_effective_policy
from signallens.domain.scheduling import next_interval_minutes
from signallens.domain.severity import clamp_severity, is_immediate
from signallens.domain.values import equivalent, value_key


def ev(cls: str, stance: str, publisher: str, quote: str = "Razorpay cut its fee to 1.8%", verified: bool = True):
    return EvidenceItem(source_class=cls, stance=stance, publisher=publisher, quote=quote, quote_verified=verified)


# --- evidence rubric --------------------------------------------------------------------------


def test_primary_support_confirms():
    a = assess([ev("primary", "supports", "razorpay.com")])
    assert a.status == "confirmed"
    assert "razorpay.com" in a.summary


def test_two_independent_publishers_corroborate():
    a = assess([
        ev("independent", "supports", "economictimes.com", "The company reduced the fee to 1.8 percent for merchants."),
        ev("independent", "supports", "livemint.com", "Merchants will now pay 1.8% instead of 2%, said the firm."),
    ])
    assert a.status == "corroborated"


def test_same_publisher_twice_is_single_source():
    a = assess([ev("independent", "supports", "inc42.com", "a"), ev("independent", "supports", "inc42.com", "b")])
    assert a.status == "single_source"


def test_syndicated_copies_count_once():
    wire = "Razorpay on Monday announced a reduction in its standard transaction fee to 1.8 per cent for all merchants."
    a = assess([ev("independent", "supports", "site-a.com", wire), ev("independent", "supports", "site-b.com", wire)])
    assert a.status == "single_source"


def test_unverified_quotes_do_not_count():
    a = assess([ev("primary", "supports", "razorpay.com", verified=False)])
    assert a.status == "unverified"
    assert a.notes


def test_primary_contradiction_is_conflicting():
    a = assess([ev("independent", "supports", "blog.com"), ev("primary", "contradicts", "razorpay.com", "2%")])
    assert a.status == "conflicting"


def test_primary_sources_disagreeing_is_conflicting():
    a = assess([ev("primary", "supports", "razorpay.com"), ev("primary", "contradicts", "razorpay.com", "Fee: 2%")])
    assert a.status == "conflicting"


def test_independent_disagreement_is_conflicting():
    a = assess([ev("independent", "supports", "a.com", "x" * 10), ev("independent", "contradicts", "b.com", "y" * 10)])
    assert a.status == "conflicting"


def test_confirmed_notes_secondary_disagreement():
    a = assess([ev("primary", "supports", "razorpay.com"), ev("independent", "contradicts", "oldnews.com", "fee is 2%")])
    assert a.status == "confirmed"
    assert any("report otherwise" in n for n in a.notes)


def test_distrusted_publisher_not_counted():
    items = [ev("independent", "supports", "a.com", "one"), ev("independent", "supports", "b.com", "two")]
    assert assess(items).status == "corroborated"
    assert assess(items, distrusted_publishers={"b.com"}).status == "single_source"


def test_context_stance_never_counts():
    assert assess([ev("primary", "context", "razorpay.com")]).status == "unverified"


def test_classify_source():
    assert classify_source("https://razorpay.com/pricing/", entity_domains=["razorpay.com"]) == "primary"
    assert classify_source("https://www.rbi.org.in/Scripts/x.aspx") == "primary"  # regulator registry
    assert classify_source("https://economictimes.indiatimes.com/x") == "independent"
    assert classify_source("https://www.reddit.com/r/india/x") == "community"
    assert classify_source("https://economictimes.indiatimes.com/x", distrusted_publishers=["indiatimes.com"]) == "community"
    assert classify_source("sandbox://nimbus-pay-pricing") == "primary"


# --- policy, thresholds, severity -------------------------------------------------------------------

SPEC = {"areas": [
    {"key": "pricing", "label": "Pricing", "importance": "critical", "route_to": ["Strategy"]},
    {"key": "products", "label": "Products", "importance": "high"},
    {"key": "funding", "label": "Funding", "importance": "low"},
]}


@dataclass
class Rule:
    kind: str
    scope: dict
    effect: dict
    explanation: str = "because"
    active: bool = True


def test_thresholds_follow_importance():
    p = build_effective_policy(SPEC, [])
    assert p.threshold_for("pricing", "pricing") == "low"
    assert p.threshold_for("products", "item_added") == "medium"
    assert p.threshold_for("funding", "funding") == "high"
    assert p.is_material("low", "pricing", "pricing")
    assert not p.is_material("low", "products", "content_change")
    assert not p.is_material("none", "pricing", "pricing")


def test_learned_rules_adjust_policy():
    rules = [
        Rule("materiality_threshold", {"area": "products", "event_type": "content_change"}, {"threshold": "high"}),
        Rule("area_importance", {"area": "funding"}, {"importance": "critical"}),
        Rule("publisher_trust", {"publisher": "rumours.com"}, {"trust": "distrusted"}),
        Rule("area_importance", {"area": "pricing"}, {"importance": "low"}, active=False),
    ]
    p = build_effective_policy(SPEC, rules)
    assert p.threshold_for("products", "content_change") == "high"
    assert p.threshold_for("products", "item_added") == "medium"
    assert p.area("funding").effective_importance == "critical"
    assert p.threshold_for("funding", "funding") == "low"
    assert "rumours.com" in p.distrusted_publishers
    assert p.area("pricing").effective_importance == "critical"  # inactive rule ignored
    assert "because" in p.describe_for_prompt()


def test_unknown_area_falls_back():
    p = build_effective_policy(SPEC, [])
    assert p.area("weird").threshold == "medium"


@pytest.mark.parametrize(("proposed", "status", "importance", "expected"), [
    ("critical", "unverified", "critical", "medium"),
    ("critical", "single_source", "critical", "high"),
    ("critical", "confirmed", "critical", "critical"),
    ("high", "corroborated", "low", "medium"),
    ("bogus", "confirmed", "high", "medium"),
])
def test_severity_caps(proposed, status, importance, expected):
    assert clamp_severity(proposed, evidence_status=status, area_importance=importance)[0] == expected


def test_immediate_delivery():
    assert is_immediate("high", "high")
    assert not is_immediate("medium", "critical")
    assert not is_immediate("critical", "low")


# --- feedback → learned rules -------------------------------------------------------------------------


def fctx(**kw):
    base = dict(verdict="not_relevant", reason="too_minor", area="products", area_label="Products",
                event_type="content_change", event_type_label="Content change", entity_name="Razorpay",
                report_title="Razorpay reworded its product page", effective_importance="high",
                current_threshold="medium")
    base.update(kw)
    return FeedbackContext(**base)


def test_too_minor_needs_two_signals():
    assert interpret(fctx(prior_same_signal=0)).proposals == []
    out = interpret(fctx(prior_same_signal=1))
    assert out.proposals[0].kind == "materiality_threshold"
    assert out.proposals[0].effect == {"threshold": "high"}
    assert "2" in out.proposals[0].explanation


def test_not_our_area_lowers_importance():
    out = interpret(fctx(reason="not_our_area", effective_importance="medium"))
    assert out.proposals[0].effect == {"importance": "low"}
    assert "digest" in out.message


def test_always_urgent_raises_to_critical():
    out = interpret(fctx(verdict="relevant", reason="always_urgent", area="regulation", area_label="Regulation"))
    assert out.proposals[0].effect == {"importance": "critical"}


def test_inaccurate_single_source_distrusts_publisher():
    out = interpret(fctx(reason="inaccurate", independent_publishers=["rumours.com"]))
    assert out.proposals[0].kind == "publisher_trust"
    assert out.proposals[0].scope == {"publisher": "rumours.com"}


def test_inaccurate_multi_source_downgrades_nobody():
    out = interpret(fctx(reason="inaccurate", independent_publishers=["a.com", "b.com"]))
    assert out.proposals == []


def test_useful_learns_nothing():
    assert interpret(fctx(verdict="relevant", reason="useful")).proposals == []


# --- clustering, scheduling, values -----------------------------------------------------------------------


def test_cluster_keys_are_structural():
    a = cluster_key("partnership", "Razorpay", counterparty="Mastercard Inc.")
    b = cluster_key("partnership", "Razorpay Software Pvt Ltd", counterparty="Mastercard")
    assert a == b == "partnership:razorpay:mastercard"
    assert cluster_key("leadership", "Razorpay", person="Jane Doe") == "leadership:razorpay:jane-doe"
    assert slug("Crème Brûlée & Co.") == "creme-brulee-co"


def test_titles_similar():
    assert titles_similar("Razorpay partners with Mastercard for tokenisation",
                          "Mastercard and Razorpay partner on tokenisation")
    assert not titles_similar("Razorpay raises funding", "Stripe launches new checkout")


def test_adaptive_intervals():
    assert next_interval_minutes(kind="page", base=60, current=60, outcome="unchanged", failures=0) == 90
    assert next_interval_minutes(kind="page", base=60, current=200, outcome="unchanged", failures=0) == 240
    assert next_interval_minutes(kind="page", base=60, current=240, outcome="changed", failures=0) == 60
    assert next_interval_minutes(kind="page", base=60, current=60, outcome="error", failures=3) == 480
    assert next_interval_minutes(kind="news", base=120, current=999, outcome="unchanged", failures=0) == 120


def test_value_equivalence_ignores_phrasing():
    prev = {"display": "2% per transaction", "number": 2.0, "unit": "%", "conditions": None}
    assert equivalent(prev, display="2 % flat per txn", number=2, unit="percent", conditions=None)
    assert not equivalent(prev, display="1.8% per transaction", number=1.8, unit="%", conditions=None)
    assert equivalent(prev, display="anything", number=None, unit=None, conditions=None, same_as_previous=True)
    text_prev = {"display": "T+2 working days"}
    assert not equivalent(text_prev, display="T+1 working day", number=None, unit=None, conditions=None)
    assert value_key(display="2%", number=2.0, unit="%", conditions="") == value_key(
        display="two percent", number=2, unit="percent", conditions=None)


def test_relative_quality_uses_neighbouring_version():
    from signallens.pipeline.quality import relative_verdict

    assert relative_verdict(350, None, None) == (True, None)  # first version: absolute checks only
    assert relative_verdict(2150, 350, None)[0]  # pages grow; growth is never suspicious
    accepted, _ = relative_verdict(300, 2100, None)
    assert not accepted  # a sudden shrink looks like a broken capture...
    accepted, note = relative_verdict(310, 2100, 300)
    assert accepted and "restructured" in note  # ...unless two consecutive versions agree


def test_date_changes_are_noise_only_in_timestamp_lines():
    from signallens.domain.diffing import diff_lines, drop_noise_hunks

    stamp = diff_lines(["Pricing", "Last updated: 1 Sep 2026"], ["Pricing", "Last updated: 28 Sep 2026"])
    kept, dropped = drop_noise_hunks(stamp)
    assert stamp.is_empty and kept.is_empty and not dropped  # masked before diffing: never even a hunk

    deadline = diff_lines(["Pricing", "Offer valid till 30 Sep 2026"], ["Pricing", "Offer valid till 31 Oct 2026"])
    kept, _ = drop_noise_hunks(deadline)
    assert not kept.is_empty  # an extended offer is a business change

    today = diff_lines(["Sep 27, 2026", "Plans"], ["Sep 28, 2026", "Plans"])
    assert drop_noise_hunks(today)[0].is_empty  # a date-only line (a "today" widget) is noise
