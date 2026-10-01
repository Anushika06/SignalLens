"""Agent runs: the full, inspectable trace of what each agent did and what it cost."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from signallens.api import schemas as S
from signallens.api.deps import get_workspace, session
from signallens.db.models import AgentRun, RunStep, Workspace

router = APIRouter(prefix="/workspaces/{wid}/runs", tags=["runs"])


def _usage(run: AgentRun) -> S.UsageOut:
    u = run.usage or {}
    return S.UsageOut(llm_calls=u.get("llm_calls", 0), tool_calls=u.get("tool_calls", 0),
                      input_tokens=u.get("input_tokens", 0), output_tokens=u.get("output_tokens", 0),
                      est_cost_usd=u.get("est_cost_usd", 0.0))


def summary(run: AgentRun) -> S.RunSummary:
    return S.RunSummary(id=str(run.id), agent=run.agent, status=run.status, title=run.title,
                        subject=S.SubjectRef(type=run.subject_type, id=str(run.subject_id)) if run.subject_id else None,
                        started_at=run.started_at, finished_at=run.finished_at, usage=_usage(run))


@router.get("", response_model=list[S.RunSummary])
async def runs(agent: str | None = None, limit: int = 30, ws: Workspace = Depends(get_workspace),
               s: AsyncSession = Depends(session)):
    q = select(AgentRun).where(AgentRun.workspace_id == ws.id)
    if agent:
        q = q.where(AgentRun.agent == agent)
    rows = (await s.execute(q.order_by(AgentRun.created_at.desc()).limit(max(1, min(limit, 200))))).scalars()
    return [summary(r) for r in rows]


@router.get("/{run_id}", response_model=S.RunDetail)
async def run_detail(run_id: uuid.UUID, ws: Workspace = Depends(get_workspace), s: AsyncSession = Depends(session)):
    run = await s.get(AgentRun, run_id)
    if run is None or run.workspace_id != ws.id:
        raise HTTPException(status_code=404, detail="Run not found")
    steps = (await s.execute(select(RunStep).where(RunStep.run_id == run.id).order_by(RunStep.idx))).scalars()
    b = run.budget or {}
    return S.RunDetail(
        **summary(run).model_dump(), task=run.task or {},
        budget=S.BudgetOut(max_steps=b.get("max_steps", 0), max_tool_calls=b.get("max_tool_calls", 0),
                           max_seconds=b.get("max_seconds", 0), max_cost_usd=b.get("max_cost_usd", 0)),
        result=run.result, error=run.error,
        steps=[S.RunStepOut(idx=st.idx, kind=st.kind, name=st.name, summary=st.summary,
                            input=_unwrap(st.input), output=_unwrap(st.output), tokens_in=st.tokens_in,
                            tokens_out=st.tokens_out, latency_ms=st.latency_ms, created_at=st.created_at)
               for st in steps],
    )


def _unwrap(value):
    if isinstance(value, dict) and set(value) == {"value"}:
        return value["value"]
    return value
