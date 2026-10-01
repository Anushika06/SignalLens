"""The effective monitoring policy: the approved plan plus active learned rules.

The approved plan says what the user asked for; learned rules (from feedback) adjust it.
Everything downstream — materiality thresholds, severity caps, routing, triage context —
reads this one object, so a learned rule's effect is predictable and reversible.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from signallens.domain.levels import IMPORTANCE, MATERIALITY, at_least, coerce, rank

# How material a change must be before we spend an investigation on it, per area importance.
BASE_THRESHOLD = {"critical": "low", "high": "medium", "medium": "medium", "low": "high"}


@dataclass
class AreaPolicy:
    key: str
    label: str
    importance: str
    effective_importance: str
    threshold: str
    route_to: list[str] = field(default_factory=list)
    description: str = ""


@dataclass
class EffectivePolicy:
    areas: dict[str, AreaPolicy]
    # (area, event_type or "*") -> minimum materiality raised by feedback
    type_thresholds: dict[tuple[str, str], str] = field(default_factory=dict)
    distrusted_publishers: set[str] = field(default_factory=set)
    exclusions: list[str] = field(default_factory=list)
    preference_notes: list[str] = field(default_factory=list)

    def area(self, key: str | None) -> AreaPolicy:
        if key and key in self.areas:
            return self.areas[key]
        return AreaPolicy(key or "general", (key or "General").replace("_", " ").title(), "medium", "medium", "medium")

    def threshold_for(self, area: str | None, event_type: str | None) -> str:
        a = self.area(area)
        threshold = a.threshold
        for key in ((a.key, event_type or ""), (a.key, "*")):
            if key in self.type_thresholds and rank(MATERIALITY, self.type_thresholds[key]) > rank(MATERIALITY, threshold):
                threshold = self.type_thresholds[key]
        return threshold

    def is_material(self, materiality: str | None, area: str | None, event_type: str | None) -> bool:
        return materiality not in (None, "none") and at_least(
            MATERIALITY, materiality, self.threshold_for(area, event_type)
        )

    def describe_for_prompt(self) -> str:
        """Compact policy description given to triage/materiality models."""
        lines = ["Monitored areas (importance → alert threshold):"]
        for a in self.areas.values():
            lines.append(f"- {a.key} ({a.label}): {a.effective_importance} → alerts at {a.threshold}+ materiality."
                         + (f" {a.description}" if a.description else ""))
        if self.preference_notes:
            lines.append("Learned user preferences:")
            lines.extend(f"- {n}" for n in self.preference_notes)
        if self.exclusions:
            lines.append("The user said these items were about the wrong company; avoid similar mismatches:")
            lines.extend(f"- {x}" for x in self.exclusions)
        return "\n".join(lines)


def build_effective_policy(spec: dict[str, Any] | None, rules: list[Any]) -> EffectivePolicy:
    """``rules`` are LearnedRule rows (or objects with kind/scope/effect/explanation/active)."""
    areas: dict[str, AreaPolicy] = {}
    for a in (spec or {}).get("areas", []):
        if not a.get("enabled", True):
            continue
        importance = coerce(IMPORTANCE, a.get("importance"), "medium")
        areas[a["key"]] = AreaPolicy(
            key=a["key"],
            label=a.get("label") or a["key"].title(),
            importance=importance,
            effective_importance=importance,
            threshold=BASE_THRESHOLD[importance],
            route_to=list(a.get("route_to") or []),
            description=a.get("description") or "",
        )

    policy = EffectivePolicy(areas=areas)
    for rule in rules:
        if not getattr(rule, "active", True):
            continue
        scope, effect = rule.scope or {}, rule.effect or {}
        if rule.kind == "area_importance" and scope.get("area") in areas:
            a = areas[scope["area"]]
            a.effective_importance = coerce(IMPORTANCE, effect.get("importance"), a.importance)
            a.threshold = BASE_THRESHOLD[a.effective_importance]
            policy.preference_notes.append(rule.explanation)
        elif rule.kind == "materiality_threshold":
            key = (scope.get("area") or "*", scope.get("event_type") or "*")
            policy.type_thresholds[key] = coerce(MATERIALITY, effect.get("threshold"), "medium")
            policy.preference_notes.append(rule.explanation)
        elif rule.kind == "publisher_trust" and scope.get("publisher"):
            policy.distrusted_publishers.add(scope["publisher"])
        elif rule.kind == "entity_exclusion" and effect.get("example"):
            policy.exclusions.append(str(effect["example"]))
    return policy
