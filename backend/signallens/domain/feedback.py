"""Feedback → learned rules (spec review C10).

Each feedback reason maps to one explainable policy adjustment. Rules are shown to the
user in plain language and can be undone; nothing is learned silently.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from signallens.domain.levels import IMPORTANCE, MATERIALITY, rank, step

TOO_MINOR_SIGNALS_NEEDED = 2

REASON_MESSAGES = {
    "useful": "Thanks — noted as useful.",
    "already_known": "Noted — 'already knew' helps us measure how early we catch things.",
    "duplicate": "Thanks — duplicates help us tune how events are merged.",
    "other": "Thanks for the feedback.",
}


@dataclass
class FeedbackContext:
    verdict: str
    reason: str
    area: str
    area_label: str
    event_type: str
    event_type_label: str
    entity_name: str | None
    report_title: str
    effective_importance: str
    current_threshold: str
    independent_publishers: list[str] = field(default_factory=list)
    primary_publishers: list[str] = field(default_factory=list)
    prior_same_signal: int = 0  # earlier feedback with the same reason/area/type (excluding this one)


@dataclass
class RuleProposal:
    kind: str
    scope: dict[str, Any]
    effect: dict[str, Any]
    explanation: str


@dataclass
class FeedbackOutcome:
    proposals: list[RuleProposal]
    message: str


def interpret(ctx: FeedbackContext) -> FeedbackOutcome:
    reason = ctx.reason
    area_l = ctx.area_label.lower()

    if reason == "too_minor":
        signals = ctx.prior_same_signal + 1
        if signals < TOO_MINOR_SIGNALS_NEEDED:
            return FeedbackOutcome(
                [], f"Noted. One more signal like this and I'll raise the bar for {ctx.event_type_label.lower()} "
                    f"items in {area_l}."
            )
        new_threshold = step(MATERIALITY, ctx.current_threshold, +1)
        if rank(MATERIALITY, new_threshold) <= rank(MATERIALITY, ctx.current_threshold):
            return FeedbackOutcome([], f"The bar for {area_l} is already at its highest setting.")
        explanation = (
            f"Because you marked {signals} {ctx.event_type_label.lower()} items in {area_l} as too minor, "
            f"I now only alert on {new_threshold} or higher materiality there."
        )
        return FeedbackOutcome(
            [RuleProposal("materiality_threshold", {"area": ctx.area, "event_type": ctx.event_type},
                          {"threshold": new_threshold}, explanation)],
            explanation,
        )

    if reason == "not_our_area":
        new_importance = step(IMPORTANCE, ctx.effective_importance, -1)
        if new_importance == ctx.effective_importance:
            return FeedbackOutcome([], f"{ctx.area_label} is already at the lowest importance.")
        explanation = (
            f"You said {area_l} isn't your area, so I lowered it from {ctx.effective_importance} to "
            f"{new_importance} importance"
            + (" — these items now go to the digest instead of immediate alerts." if new_importance == "low" else ".")
        )
        return FeedbackOutcome(
            [RuleProposal("area_importance", {"area": ctx.area}, {"importance": new_importance}, explanation)],
            explanation,
        )

    if reason == "always_urgent":
        if ctx.effective_importance == "critical":
            return FeedbackOutcome([], f"{ctx.area_label} is already critical — you'll be told immediately.")
        explanation = f"You asked to always hear about {area_l} immediately — it is now critical importance."
        return FeedbackOutcome(
            [RuleProposal("area_importance", {"area": ctx.area}, {"importance": "critical"}, explanation)],
            explanation,
        )

    if reason == "inaccurate":
        if not ctx.primary_publishers and len(ctx.independent_publishers) == 1:
            publisher = ctx.independent_publishers[0]
            explanation = (
                f"You flagged an item that rested only on {publisher} as inaccurate, so {publisher} no longer "
                f"counts towards corroboration in this workspace."
            )
            return FeedbackOutcome(
                [RuleProposal("publisher_trust", {"publisher": publisher}, {"trust": "distrusted"}, explanation)],
                explanation,
            )
        return FeedbackOutcome(
            [], "Flagged as inaccurate. It rested on several sources, so no single publisher was downgraded."
        )

    if reason == "wrong_entity":
        example = ctx.report_title
        explanation = (
            f"You said “{example}” was about a different company than {ctx.entity_name or 'the one we track'}; "
            "I'll screen out similar mismatches."
        )
        return FeedbackOutcome(
            [RuleProposal("entity_exclusion", {"entity": ctx.entity_name or ""}, {"example": example}, explanation)],
            explanation,
        )

    return FeedbackOutcome([], REASON_MESSAGES.get(reason, REASON_MESSAGES["other"]))
