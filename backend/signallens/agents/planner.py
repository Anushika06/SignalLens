"""Planner: understands the request, researches the subject, and proposes a monitoring plan.

Two phases: an agent loop that researches with tools (search, open pages), then one
structured call that turns the research into a ``MonitoringPlanOut``. The plan is then
validated live by the pipeline (reachability, robots.txt, content quality) and shown to
a human for approval — nothing is monitored before that.
"""

from __future__ import annotations

from typing import Any

from signallens.agents import prompts
from signallens.agents.schemas import MonitoringPlanOut, PlannerFinish
from signallens.runtime.core import LoopAgent, RunContext
from signallens.tools.research import OpenPageTool, SearchNewsTool, SearchWebTool


class PlannerAgent(LoopAgent):
    name = "planner"

    def __init__(self, *, search_available: bool):
        tools = [SearchWebTool(), SearchNewsTool(), OpenPageTool()] if search_available else [OpenPageTool()]
        system = prompts.PLANNER
        if not search_available:
            system += ("\nSearch is not available in this deployment. Use your knowledge to propose the official "
                       "website and likely pages, and open them to verify before relying on them.\n")
        super().__init__(
            system_prompt=system,
            tools=tools,
            finish_schema=PlannerFinish,
            finish_description=("finish(notes: str) - call when you know enough to plan. Put everything useful "
                                "in notes, including every verified URL and what it shows."),
        )

    async def review_finish(self, ctx: RunContext, final: Any, *, objections_so_far: int) -> str | None:
        if objections_so_far == 0 and not ctx.documents:
            return ("You have not opened any page yet. Open the subject's official website (and its pricing or "
                    "products page) so the plan only uses verified URLs, then finish.")
        return None


def profile_text(profile: dict[str, Any] | None) -> str:
    p = profile or {}
    if not (p.get("company_name") or p.get("description")):
        return "(not provided)"
    parts = [
        f"Company: {p.get('company_name') or 'unknown'}" + (f" ({p['website']})" if p.get("website") else ""),
        f"What we do: {p.get('description') or 'n/a'}",
        f"Products: {', '.join(p.get('products') or []) or 'n/a'}",
        f"Markets: {', '.join(p.get('markets') or []) or 'n/a'}",
        f"Known competitors: {', '.join(p.get('competitors') or []) or 'n/a'}",
        f"Relationship to monitored subjects: {p.get('relationship_to_subjects') or 'n/a'}",
    ]
    return "\n".join(parts)


def research_task(request_text: str, profile: dict[str, Any] | None, today: str) -> str:
    return (f"TODAY: {today}\n\nUSER REQUEST:\n{request_text}\n\nTHE USER'S OWN COMPANY (context for relevance):\n"
            f"{profile_text(profile)}\n\nResearch what is needed to plan monitoring for this request.")


async def compose_plan(
    ctx: RunContext,
    *,
    request_text: str,
    profile: dict[str, Any] | None,
    team_names: list[str],
    notes: str,
    research_log: list[dict[str, Any]],
    today: str,
) -> MonitoringPlanOut:
    log_lines = []
    for entry in research_log[-14:]:
        log_lines.append(f"## {entry['action']} {entry['args']}\n{entry['result'][:1200]}")
    prompt = (
        f"TODAY: {today}\n\nUSER REQUEST:\n{request_text}\n\nUSER'S COMPANY PROFILE:\n{profile_text(profile)}\n\n"
        f"TEAMS (use these names in route_to): {', '.join(team_names) or 'Strategy'}\n\n"
        f"RESEARCH NOTES:\n{notes}\n\nRESEARCH LOG (tool results, truncated):\n<untrusted_content>\n"
        + "\n\n".join(log_lines) + "\n</untrusted_content>\n\nWrite the monitoring plan."
    )
    return await ctx.services.require_llm().structured(
        MonitoringPlanOut, tier="reasoning", system=prompts.PLAN_COMPOSER, messages=prompt, ctx=ctx,
        purpose="Compose monitoring plan", max_tokens=16000,
    )
