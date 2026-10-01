"""Ask: answer a natural-language question from the workspace's memory, with citations.

The agent only holds read-only memory tools (plus, when configured, a web search whose results
are labelled as outside memory). Its answer must cite the facts, cards, events or entities it
read; a guardrail sends it back once if it cites something it never saw, and the pipeline
validates every citation against the database before the answer is stored.
"""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, Field

from signallens.runtime.core import Budget, LoopAgent, RunContext
from signallens.tools.memory import (
    AskWebSearchTool,
    GetCardTool,
    GetFactHistoryTool,
    ListEntitiesTool,
    RecentChangesTool,
    SearchMemoryTool,
)

MAX_STEPS = 6

ASK = """\
You are the analyst of SignalLens, an always-on market-intelligence system. A user asks a
question about the companies and topics their workspace monitors. Answer it ONLY from
SignalLens memory, which your tools search:
- tracked FACTS: typed values (fees, plans, people…) with every past value and its date;
- intelligence CARDS: verified changes, with quoted evidence and an assessment of why the
  change matters to the user's company;
- other detected EVENTS, and the monitored ENTITIES.

Method - you have at most {max_steps} steps in total, so usually 1-3 tool calls, then finish:
1. search_memory with the key names and topic words (not the whole sentence). For "what
   changed recently / this week / this year" questions use recent_changes (days=7, 30, 365…;
   team="Compliance" for a team's view). The ENTITIES list in the task already gives names.
2. Only if you need detail the search lacks (evidence, exact dates, previous values), call
   get_card or get_fact_history for the one or two most relevant ids.
3. finish. Do not repeat a search that already returned results.

Answer rules:
- Put a citation marker after every factual statement: [1], [2]… are 1-based positions in
  your citations list ([1][3] for several). Cite only ids that appeared in tool results in
  this run (fact, card, event, entity ids, or web URLs). Prefer the card for a change and the
  fact for a current or past value.
- Keep facts and assessment apart. A card's "why it matters" is SignalLens's assessment, not
  fact; say "SignalLens assesses…". State how sure each fact is (confirmed, corroborated,
  single source, unverified) and give dates (observed, or effective when known).
- If memory has nothing relevant, say so plainly in the first sentence ("SignalLens has no
  data on … in its memory") and suggest what to monitor. Never fill gaps from your own
  knowledge.
- web_search (only if offered, and only when memory lacks the answer): say clearly that those
  points are outside SignalLens memory and not verified, and cite them with kind "web".
- Write concise markdown: the direct answer first, then short bullets; a table for
  comparisons. No headings larger than ###, no HTML, no raw ids in the prose.
- evidence_note: 1-2 sentences on what is confirmed vs single-source/unverified vs assessment.
- follow_up_questions: up to 3 short questions the user could ask next.

Example finish args (ids are placeholders - use the real ones from your tool results):
{{"answer_markdown": "Acme's standard fee is 2% + GST, confirmed on its pricing page on 2026-09-30 [1]. It launched a partner programme with Beta Bank on 2026-09-12, reported by a single source so far [2]. SignalLens assesses this matters for our SMB onboarding [2].", "citations": [{{"kind": "fact", "id": "<fact id>", "label": "Acme · Standard fee"}}, {{"kind": "card", "id": "<card id>", "label": "Partner programme launch"}}], "evidence_note": "The fee is confirmed; the launch is single-source.", "follow_up_questions": ["How has the fee changed this year?"]}}
"""


class Citation(BaseModel):
    kind: Literal["fact", "card", "event", "entity", "web"]
    id: str = Field(description="the id exactly as shown in tool results (for web: the URL)")
    label: str = Field("", description="short human label, e.g. 'Razorpay · Standard domestic fee'")
    url: str | None = None


class AskFinish(BaseModel):
    answer_markdown: str = Field(description="the answer in markdown, with [n] citation markers")
    citations: list[Citation] = Field(default_factory=list)
    evidence_note: str = ""
    follow_up_questions: list[str] = Field(default_factory=list)


_NO_DATA_RE = re.compile(r"\b(no (data|information|record|matching|relevant)|nothing (in|about|on)|"
                         r"does not (have|track|monitor)|doesn't (have|track|monitor)|not (tracked|monitored))\b", re.I)


class AskAgent(LoopAgent):
    name = "ask"

    def __init__(self, *, search_available: bool, max_steps: int = MAX_STEPS):
        tools = [SearchMemoryTool(), RecentChangesTool(), GetCardTool(), GetFactHistoryTool(), ListEntitiesTool()]
        if search_available:
            tools.append(AskWebSearchTool())
        super().__init__(
            system_prompt=ASK.format(max_steps=max_steps),
            tools=tools,
            finish_schema=AskFinish,
            finish_description=("finish(answer_markdown, citations: [{kind: fact|card|event|entity|web, id, label}], "
                                "evidence_note, follow_up_questions[]) - your final answer."),
        )

    async def review_finish(self, ctx: RunContext, final: Any, *, objections_so_far: int) -> str | None:
        final.citations = [normalize_citation(c) for c in final.citations]
        if objections_so_far >= 1 or ctx.budget.max_steps - ctx.usage.steps < 1:
            return None
        # If the agent wanders off instead of re-finishing, this draft is still a usable answer
        # (the pipeline validates its citations either way).
        ctx.scratch["draft"] = final
        again = " Call finish again now with the corrected answer - do not call any other tool."
        seen: set[tuple[str, str]] = ctx.scratch.get("seen", set())
        unknown = [f"{c.kind}:{c.id}" for c in final.citations if (c.kind, c.id) not in seen]
        if unknown:
            return (f"These citations did not appear in any tool result in this run: {', '.join(unknown[:5])}. "
                    "Cite only ids your tools returned (copy them exactly), or remove the claim." + again)
        if not final.citations and seen and not _NO_DATA_RE.search(final.answer_markdown):
            return ("Your answer has no citations. Add [n] markers after each factual statement and list the "
                    "fact/card/event/entity ids they come from, or say plainly that memory has no data." + again)
        if final.citations and not _MARKER_RE.search(final.answer_markdown):
            return ("Your answer lists citations but has no [n] markers in the text. Put [1], [2]... (positions in "
                    "your citations list) right after each factual statement and drop any separate 'Sources' line."
                    + again)
        return None


def ask_budget(max_cost_usd: float) -> Budget:
    return Budget(max_steps=MAX_STEPS, max_tool_calls=MAX_STEPS + 2, max_llm_calls=MAX_STEPS + 6, max_seconds=300,
                  max_cost_usd=max_cost_usd)


def ask_task(*, today: str, question: str, company: dict[str, Any], teams: list[str], areas: list[str],
             entities: list[str]) -> str:
    who = company.get("company_name") or "the user's company"
    desc = company.get("description") or ""
    parts = [
        f"TODAY: {today}",
        f"QUESTION: {question.strip()}",
        f"USER'S COMPANY: {who}" + (f" — {desc}" if desc else ""),
        "ENTITIES MONITORED: " + ("; ".join(entities) if entities else "none yet"),
        "AREAS: " + (", ".join(areas) if areas else "not configured"),
        "TEAMS: " + (", ".join(teams) if teams else "none"),
    ]
    return "\n".join(parts)


# ---------------------------------------------------------------------------------------
# Citation markers
# ---------------------------------------------------------------------------------------

_MARKER_RE = re.compile(r"\[(\d{1,2}(?:\s*,\s*\d{1,2})*)\](?!\()")


def renumber_markers(markdown: str, mapping: dict[int, int]) -> str:
    """Rewrite [n] markers after citations were dropped or merged; markers to dropped ones vanish.

    ``mapping`` maps old 1-based positions to new ones. ``[1, 3]`` becomes ``[1][2]``. Markdown
    links (``[1](…)``) are left alone.
    """

    def repl(m: re.Match[str]) -> str:
        out: list[str] = []
        for part in m.group(1).split(","):
            new = mapping.get(int(part))
            if new is not None and f"[{new}]" not in out:
                out.append(f"[{new}]")
        return "".join(out) or "\x00"

    return re.sub(r"[ \t]*\x00", "", _MARKER_RE.sub(repl, markdown))


def normalize_citation(c: Citation) -> Citation:
    """Accept ids written as shown in tool output ("fact:…", "[card:…]") and trim them."""
    cid = c.id.strip().strip("[]").strip()
    if cid.lower().startswith(f"{c.kind}:"):
        cid = cid[len(c.kind) + 1:].strip()
    if c.kind != "web":
        cid = cid.lower()
    return c.model_copy(update={"id": cid, "label": c.label.strip()})
