"""Verifier: the investigation loop.

Given a potential change, the agent decides what to look for next, opens sources,
records quoted evidence, and decides when it has enough. Guardrail: if it tries to
finish while the evidence is still single-source or unverified and budget remains, the
runtime sends it back once to look for a primary source and an independent report.
"""

from __future__ import annotations

from typing import Any

from signallens.agents import prompts
from signallens.agents.schemas import InvestigationFinish
from signallens.runtime.core import LoopAgent, RunContext
from signallens.tools.evidence import ListEvidenceTool, RecordEvidenceTool
from signallens.tools.research import (
    FactHistoryTool,
    ListArchiveCapturesTool,
    OpenArchivedPageTool,
    OpenPageTool,
    SearchNewsTool,
    SearchWebTool,
)


class InvestigatorAgent(LoopAgent):
    name = "investigator"

    def __init__(self, *, search_available: bool):
        tools = [OpenPageTool(), ListArchiveCapturesTool(), OpenArchivedPageTool(), FactHistoryTool(),
                 RecordEvidenceTool(), ListEvidenceTool()]
        if search_available:
            tools = [SearchNewsTool(), SearchWebTool(), *tools]
        super().__init__(
            system_prompt=prompts.INVESTIGATOR,
            tools=tools,
            finish_schema=InvestigationFinish,
            finish_description=("finish(conclusion, claim_holds: yes|no|partly|unclear, corrected_statement?, "
                                "occurred_at?, contradictions[], open_questions[]) - when you have enough evidence "
                                "or further search is unlikely to help."),
        )

    async def review_finish(self, ctx: RunContext, final: Any, *, objections_so_far: int) -> str | None:
        status = ctx.scratch.get("evidence_status", "unverified")
        if objections_so_far >= 1 or status not in ("single_source", "unverified"):
            return None
        room = (ctx.budget.max_tool_calls - ctx.usage.tool_calls >= 3) and (ctx.budget.max_steps - ctx.usage.steps >= 3)
        if not room:
            return None
        entity = ctx.scratch.get("entity_name") or "the entity"
        return (f"Evidence status is still '{status}'. Before finishing, make one more serious attempt: look for the "
                f"primary source (the official site or newsroom of {entity}, or the relevant regulator) and for an "
                "independent report from a different publisher. If nothing turns up, finish and say so.")


def investigation_task(
    *,
    today: str,
    claim: str,
    title: str,
    summary: str,
    entity_name: str | None,
    entity_domains: list[str],
    area_label: str,
    before: str | None,
    after: str | None,
    detection: str,
    evidence_lines: list[str],
    status: str,
    fact_history: str | None,
) -> str:
    parts = [
        f"TODAY: {today}",
        f"CLAIM TO VERIFY: {claim}",
        f"DETECTED CHANGE: {title} — {summary}",
        f"ENTITY: {entity_name or 'unknown'} (official domains: {', '.join(entity_domains) or 'unknown'})",
        f"AREA: {area_label}",
        f"HOW IT WAS DETECTED: {detection}",
    ]
    if before or after:
        parts.append(f"BEFORE: {before or 'n/a'}\nAFTER: {after or 'n/a'}")
    if fact_history:
        parts.append(f"WHAT WE ALREADY KNOW (history):\n{fact_history}")
    parts.append(f"EVIDENCE SO FAR (status: {status}):\n" + ("\n".join(evidence_lines) or "none"))
    parts.append("Pages already opened for you (quotable): the detection source above, if listed.")
    return "\n\n".join(parts)
