"""Ask: natural-language questions over the workspace's memory, answered by an agent with citations.

``POST`` queues the question and returns at once; the worker runs the Ask agent. Clients poll
``GET /ask/{run_id}`` (live steps while it works) and list past questions with ``GET /ask``.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from signallens.api import schemas as S
from signallens.api.deps import Principal, current, get_workspace, services, session
from signallens.api.routes.runs import _unwrap
from signallens.db.models import AgentRun, RunStep, Workspace
from signallens.pipeline.ask import AGENT, TooManyQuestions, create_ask
from signallens.runtime.services import Services

router = APIRouter(prefix="/workspaces/{wid}/ask", tags=["ask"])


class AskIn(BaseModel):
    question: str = Field(min_length=3, max_length=500)


class AskStarted(BaseModel):
    run_id: str
    status: str


class AskCitation(BaseModel):
    kind: Literal["fact", "card", "event", "entity", "web"]
    id: str
    label: str
    url: str | None = None
    entity_id: str | None = None
    report_id: str | None = None


class AskItem(BaseModel):
    id: str
    status: str
    question: str
    asked_by: str | None = None
    answer_markdown: str | None = None
    citations: list[AskCitation] = Field(default_factory=list)
    evidence_note: str | None = None
    follow_up_questions: list[str] = Field(default_factory=list)
    used_web: bool = False
    error: str | None = None
    steps_count: int = 0
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    usage: S.UsageOut


class AskDetail(AskItem):
    budget: S.BudgetOut
    steps: list[S.RunStepOut]


def _item(run: AgentRun, steps_count: int) -> dict[str, Any]:
    task, result, u = run.task or {}, run.result or {}, run.usage or {}
    return dict(
        id=str(run.id), status=run.status, question=task.get("question", ""), asked_by=task.get("asked_by"),
        answer_markdown=result.get("answer_markdown"), citations=result.get("citations") or [],
        evidence_note=result.get("evidence_note"), follow_up_questions=result.get("follow_up_questions") or [],
        used_web=bool(result.get("used_web")), error=run.error, steps_count=steps_count, created_at=run.created_at,
        started_at=run.started_at, finished_at=run.finished_at,
        usage=S.UsageOut(llm_calls=u.get("llm_calls", 0), tool_calls=u.get("tool_calls", 0),
                         input_tokens=u.get("input_tokens", 0), output_tokens=u.get("output_tokens", 0),
                         est_cost_usd=u.get("est_cost_usd", 0.0)),
    )


async def _run(s: AsyncSession, ws: Workspace, run_id: uuid.UUID) -> AgentRun:
    run = await s.get(AgentRun, run_id)
    if run is None or run.workspace_id != ws.id or run.agent != AGENT:
        raise HTTPException(status_code=404, detail="Question not found")
    return run


@router.post("", response_model=AskStarted, status_code=202)
async def ask(body: AskIn, ws: Workspace = Depends(get_workspace), s: AsyncSession = Depends(session),
              who: Principal = Depends(current), svc: Services = Depends(services)):
    question = body.question.strip()
    if len(question) < 3:
        raise HTTPException(status_code=422, detail="Ask a question of at least a few words")
    try:
        run = await create_ask(s, workspace_id=ws.id, question=question, user_id=who.user.id, user_name=who.user.name,
                               max_cost_usd=svc.settings.investigation_max_cost_usd)
    except TooManyQuestions as e:
        raise HTTPException(status_code=429, detail=str(e)) from e
    return AskStarted(run_id=str(run.id), status=run.status)


@router.get("", response_model=list[AskItem])
async def history(limit: int = 20, ws: Workspace = Depends(get_workspace), s: AsyncSession = Depends(session)):
    runs = (await s.execute(select(AgentRun).where(AgentRun.workspace_id == ws.id, AgentRun.agent == AGENT)
                            .order_by(AgentRun.created_at.desc()).limit(max(1, min(limit, 50))))).scalars().all()
    counts = dict((await s.execute(select(RunStep.run_id, func.count(RunStep.id))
                                   .where(RunStep.run_id.in_([r.id for r in runs])).group_by(RunStep.run_id))).all()) if runs else {}
    return [AskItem(**_item(r, counts.get(r.id, 0))) for r in runs]


@router.get("/{run_id}", response_model=AskDetail)
async def detail(run_id: uuid.UUID, ws: Workspace = Depends(get_workspace), s: AsyncSession = Depends(session)):
    run = await _run(s, ws, run_id)
    steps = (await s.execute(select(RunStep).where(RunStep.run_id == run.id).order_by(RunStep.idx))).scalars().all()
    b = run.budget or {}
    return AskDetail(
        **_item(run, len(steps)),
        budget=S.BudgetOut(max_steps=b.get("max_steps", 0), max_tool_calls=b.get("max_tool_calls", 0),
                           max_seconds=b.get("max_seconds", 0), max_cost_usd=b.get("max_cost_usd", 0)),
        steps=[S.RunStepOut(idx=st.idx, kind=st.kind, name=st.name, summary=st.summary, input=_unwrap(st.input),
                            output=_unwrap(st.output), tokens_in=st.tokens_in, tokens_out=st.tokens_out,
                            latency_ms=st.latency_ms, created_at=st.created_at) for st in steps],
    )
