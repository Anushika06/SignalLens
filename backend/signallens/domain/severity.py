"""Severity guardrails (spec review C8).

Severity (how much it matters to us) and evidence status (how sure we are) are separate
axes, but an unsure item must not be shouted about: the impact analyst proposes a
severity and these rules cap it.
"""

from __future__ import annotations

from signallens.domain.levels import SEVERITY, coerce, rank


def clamp_severity(proposed: str | None, *, evidence_status: str, area_importance: str) -> tuple[str, list[str]]:
    severity = coerce(SEVERITY, proposed, "medium")
    notes: list[str] = []
    if evidence_status == "unverified" and rank(SEVERITY, severity) > rank(SEVERITY, "medium"):
        severity = "medium"
        notes.append("Capped at medium until a source verifies it.")
    if evidence_status == "single_source" and severity == "critical":
        severity = "high"
        notes.append("Capped at high until corroborated.")
    if area_importance == "low" and rank(SEVERITY, severity) > rank(SEVERITY, "medium"):
        severity = "medium"
        notes.append("This area is marked low importance for this workspace.")
    return severity, notes


def is_immediate(severity: str, area_importance: str) -> bool:
    """Critical/high items alert their teams now; everything else goes to the digest (C11)."""
    return severity in ("critical", "high") and area_importance != "low"
