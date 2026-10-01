"""Impact analyst: one strong-model call that writes the intelligence card for *this* company."""

from __future__ import annotations

from typing import Any

from signallens.agents import prompts
from signallens.agents.planner import profile_text
from signallens.agents.schemas import ImpactOut
from signallens.runtime.core import RunContext


async def analyze_impact(
    ctx: RunContext,
    *,
    today: str,
    profile: dict[str, Any] | None,
    teams: list[str],
    area_label: str,
    area_importance: str,
    entity_name: str | None,
    event_type: str,
    title: str,
    claim: str,
    before: str | None,
    after: str | None,
    evidence_status: str,
    evidence_summary: str,
    evidence_lines: list[str],
    investigation: str | None,
    history: str | None,
    related: list[str],
    historical: bool,
    tier: str = "reasoning",
) -> ImpactOut:
    prompt = "\n\n".join(filter(None, [
        f"TODAY: {today}",
        "NOTE: this is a HISTORICAL change reconstructed from the web archive; write it as history." if historical else None,
        f"OUR COMPANY PROFILE:\n{profile_text(profile)}",
        f"TEAMS: {', '.join(teams) or 'Strategy'}",
        f"AREA: {area_label} (importance for us: {area_importance})",
        f"ENTITY: {entity_name or 'unknown'} | EVENT TYPE: {event_type}",
        f"DETECTED: {title}",
        f"CLAIM: {claim}",
        f"BEFORE: {before}" if before else None,
        f"AFTER: {after}" if after else None,
        f"EVIDENCE STATUS: {evidence_status} — {evidence_summary}",
        "EVIDENCE:\n<untrusted_content>\n" + ("\n".join(evidence_lines) or "none") + "\n</untrusted_content>",
        f"INVESTIGATION CONCLUSION: {investigation}" if investigation else None,
        f"HISTORY OF THIS FACT:\n{history}" if history else None,
        ("RELATED RECENT EVENTS:\n" + "\n".join(f"- {r}" for r in related)) if related else None,
    ]))
    return await ctx.services.require_llm().structured(
        ImpactOut, tier=tier, system=prompts.IMPACT, messages=prompt, ctx=ctx,
        purpose="Write intelligence card", max_tokens=6000,
    )
