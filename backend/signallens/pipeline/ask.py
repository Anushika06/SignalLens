"""Ask: queue a question, run the Ask agent in the worker, validate citations, store the answer.

An Ask is an ``AgentRun`` with ``agent="ask"``: ``task = {"question", "asked_by", "user_id"}``,
``result = {"answer_markdown", "citations", "evidence_note", "follow_up_questions", …}``, and
its ``RunStep`` rows are the live trace the UI polls.
"""

from __future__ import annotations

import logging
import uuid
from datetime import timedelta
from typing import Any

from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from signallens.agents.ask import (
    AskAgent,
    AskFinish,
    Citation,
    ask_budget,
    ask_task,
    normalize_citation,
    renumber_markers,
)
from signallens.db.base import utcnow
from signallens.db.models import AgentRun, Entity, Event, Fact, IntelligenceReport, Team, Workspace
from signallens.db.session import transaction
from signallens.jobs.queue import PRIORITY_INTERACTIVE, enqueue
from signallens.llm.base import ChatMessage
from signallens.pipeline.common import today_str
from signallens.runtime.core import Budget, BudgetExceeded, RunContext, Usage, finish_run
from signallens.runtime.jsonutil import jsonable
from signallens.runtime.services import NotConfigured, Services
from signallens.store.world import effective_policy

log = logging.getLogger(__name__)

AGENT = "ask"
MAX_IN_FLIGHT = 3


class TooManyQuestions(Exception):
    pass


async def create_ask(s: AsyncSession, *, workspace_id: uuid.UUID, question: str, user_id: uuid.UUID | None,
                     user_name: str | None, max_cost_usd: float) -> AgentRun:
    """Record the question as a queued run and enqueue the job, in the caller's transaction."""
    recent = utcnow() - timedelta(minutes=15)
    in_flight = (await s.execute(select(func.count(AgentRun.id)).where(
        AgentRun.workspace_id == workspace_id, AgentRun.agent == AGENT,
        AgentRun.status.in_(("queued", "running")), AgentRun.created_at >= recent))).scalar_one()
    if in_flight >= MAX_IN_FLIGHT:
        raise TooManyQuestions(f"{in_flight} questions are still being answered; wait for one to finish")
    question = " ".join(question.split())
    run = AgentRun(id=uuid.uuid4(), workspace_id=workspace_id, agent=AGENT, title=f"Ask: {question[:110]}",
                   status="queued", task={"question": question, "asked_by": user_name,
                                          "user_id": str(user_id) if user_id else None},
                   budget=ask_budget(max_cost_usd).as_dict(), usage=Usage().as_dict(), started_at=None)
    s.add(run)
    await s.flush()
    await enqueue(s, "ask", {"run_id": str(run.id)}, workspace_id=workspace_id, priority=PRIORITY_INTERACTIVE,
                  dedupe_key=f"ask:{run.id}", max_attempts=1)
    return run


async def answer_question(services: Services, run_id: uuid.UUID) -> dict[str, Any]:
    async with transaction(services.session_factory) as s:
        run = await s.get(AgentRun, run_id)
        if run is None or run.agent != AGENT:
            return {"skipped": "missing"}
        if run.status != "queued":
            if run.status == "running":  # the worker died mid-answer; don't leave it spinning forever
                run.status, run.error, run.finished_at = "failed", "Interrupted — please ask again.", utcnow()
            return {"skipped": f"status {run.status}"}
        run.status, run.started_at = "running", utcnow()
        workspace_id, question, budget = run.workspace_id, (run.task or {}).get("question", ""), dict(run.budget or {})
        ws = await s.get(Workspace, workspace_id)
        policy = await effective_policy(s, workspace_id)
        teams = (await s.execute(select(Team).where(Team.workspace_id == workspace_id).order_by(Team.name))).scalars().all()
        ents = (await s.execute(select(Entity).where(Entity.workspace_id == workspace_id)
                                .order_by(Entity.role, Entity.name).limit(40))).scalars().all()
        task = ask_task(
            today=today_str(), question=question, company=dict(ws.profile or {}) if ws else {},
            teams=[t.name + (f" (areas: {', '.join(t.areas)})" if t.areas else "") for t in teams],
            areas=[f"{a.key} = {a.label}" for a in policy.areas.values()],
            entities=[f"{e.name} ({e.role})" for e in ents],
        )

    b = Budget(**{k: v for k, v in budget.items() if k in Budget.__dataclass_fields__}) if budget else \
        ask_budget(services.settings.investigation_max_cost_usd)
    ctx = RunContext(services, run_id=run_id, workspace_id=workspace_id, agent=AGENT, budget=b)
    agent = AskAgent(search_available=services.search is not None, max_steps=b.max_steps)
    try:
        result = await agent.run(ctx, task)
        final: AskFinish | None = result.final
        synthesized = False
        if final is None and ctx.scratch.get("draft") is not None:
            final = ctx.scratch["draft"]  # a complete answer the guardrail sent back; better than none
            await ctx.step("note", "Used the answer drafted before the guardrail objection", name="finish")
        if final is None and result.research_log:
            final = await _synthesize(ctx, agent, task, result.research_log)
            synthesized = final is not None
        if final is None:
            await finish_run(ctx, "budget_exhausted", result={"question": question},
                             error=f"Stopped before an answer was ready ({result.detail or result.stop_reason}). "
                                   "Try a narrower question.")
            return {"stop": result.stop_reason}
        async with services.session_factory() as s:
            citations, mapping, dropped = await validate_citations(
                s, workspace_id, final.citations, ctx.scratch.get("web_urls", {}))
        stored = {
            "question": question,
            "answer_markdown": renumber_markers(final.answer_markdown.strip(), mapping),
            "citations": citations,
            "evidence_note": final.evidence_note.strip(),
            "follow_up_questions": [q.strip() for q in final.follow_up_questions if q.strip()][:3],
            "dropped_citations": dropped,
            "used_web": any(c["kind"] == "web" for c in citations),
            "stop_reason": result.stop_reason,
            "synthesized": synthesized,
        }
        if dropped:
            await ctx.step("guardrail", f"Dropped {dropped} citation(s) that do not exist in this workspace",
                           name="citations")
        await finish_run(ctx, "succeeded", result=stored)
        return {"citations": len(citations), "dropped": dropped}
    except NotConfigured as e:
        await finish_run(ctx, "failed", error=str(e))
        return {"error": str(e)}
    except Exception as e:  # never leave the question spinning; the job is not retried
        log.exception("ask failed")
        await finish_run(ctx, "failed", error=f"{type(e).__name__}: {e}")
        return {"error": f"{type(e).__name__}"}


async def _synthesize(ctx: RunContext, agent: AskAgent, task: str, log_: list[dict[str, Any]]) -> AskFinish | None:
    """The step budget ran out mid-research: one last model call writes the answer from what was found."""
    notes = "\n\n".join(f"{i}. {r['action']}({jsonable(r['args'])}):\n{r['result']}" for i, r in enumerate(log_[-6:], 1))
    prompt = (f"{task}\n\nYou have run out of steps. Here is everything your tools returned:\n"
              f"<untrusted_content tool=\"memory\">\n{notes}\n</untrusted_content>\n\n"
              "Write the final answer now from this material only, following the answer rules.")
    try:
        final, _meta = await ctx.services.require_llm().structured_with_meta(
            AskFinish, tier="reasoning", system=agent.system_prompt, messages=[ChatMessage(role="user", content=prompt)],
            ctx=ctx, purpose="ask: final answer from research so far")
    except (BudgetExceeded, ValidationError) as e:
        await ctx.step("guardrail", f"Could not write a final answer: {e}", name="budget")
        return None
    except Exception as e:
        log.warning("ask synthesis failed: %s", e)
        await ctx.step("error", f"Could not write a final answer: {type(e).__name__}", name="finish")
        return None
    return final


def _uuid(value: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(value)
    except (ValueError, TypeError):
        return None


async def resolve_citation(s: AsyncSession, workspace_id: uuid.UUID, c: Citation,
                           web_urls: dict[str, str]) -> dict[str, Any] | None:
    """The citation as stored (labels come from the database, not the model), or None if invalid."""
    if c.kind == "web":
        if c.id not in web_urls or not c.id.startswith(("https://", "http://")):
            return None
        return {"kind": "web", "id": c.id, "label": (web_urls[c.id] or c.id)[:140], "url": c.id}
    oid = _uuid(c.id)
    if oid is None:
        return None
    if c.kind == "fact":
        row = (await s.execute(select(Fact, Entity).join(Entity, Entity.id == Fact.entity_id)
                               .where(Fact.id == oid, Fact.workspace_id == workspace_id))).first()
        if row is None:
            return None
        f, e = row
        return {"kind": "fact", "id": str(f.id), "label": f"{e.name} · {f.label}"[:140], "entity_id": str(e.id)}
    if c.kind == "card":
        r = await s.get(IntelligenceReport, oid)
        if r is None or r.workspace_id != workspace_id:
            return None
        return {"kind": "card", "id": str(r.id), "label": r.title[:140],
                "entity_id": str(r.entity_id) if r.entity_id else None}
    if c.kind == "event":
        ev = await s.get(Event, oid)
        if ev is None or ev.workspace_id != workspace_id:
            return None
        rid = (await s.execute(select(IntelligenceReport.id).where(IntelligenceReport.event_id == ev.id))).scalar_one_or_none()
        return {"kind": "event", "id": str(ev.id), "label": ev.title[:140], "report_id": str(rid) if rid else None,
                "entity_id": str(ev.entity_id) if ev.entity_id else None}
    if c.kind == "entity":
        e = await s.get(Entity, oid)
        if e is None or e.workspace_id != workspace_id:
            return None
        return {"kind": "entity", "id": str(e.id), "label": e.name[:140]}
    return None


async def validate_citations(s: AsyncSession, workspace_id: uuid.UUID, citations: list[Citation],
                             web_urls: dict[str, str]) -> tuple[list[dict[str, Any]], dict[int, int], int]:
    """Keep citations that exist in this workspace; merge duplicates.

    Returns (citations, old→new 1-based position map for the [n] markers, number dropped).
    """
    out: list[dict[str, Any]] = []
    mapping: dict[int, int] = {}
    positions: dict[tuple[str, str], int] = {}
    dropped = 0
    for i, raw in enumerate(citations, 1):
        resolved = await resolve_citation(s, workspace_id, normalize_citation(raw), web_urls)
        if resolved is None:
            dropped += 1
            continue
        key = (resolved["kind"], resolved["id"])
        if key not in positions:
            out.append(resolved)
            positions[key] = len(out)
        mapping[i] = positions[key]
    return out, mapping, dropped
