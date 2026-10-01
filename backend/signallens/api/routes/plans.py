"""Onboarding: request → planning agent → plan review → human approval."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from signallens.api import schemas as S
from signallens.api.deps import Principal, current, get_workspace, session
from signallens.api.views import sid
from signallens.db.models import MonitoringPolicy, Workspace
from signallens.jobs.queue import PRIORITY_INTERACTIVE, enqueue
from signallens.pipeline.activation import activate_plan
from signallens.plan import MonitoringPlan

router = APIRouter(prefix="/workspaces/{wid}/plans", tags=["plans"])


def plan_out(p: MonitoringPolicy) -> S.PlanDetail:
    return S.PlanDetail(id=str(p.id), version=p.version, status=p.status, request_text=p.request_text,
                        run_id=sid(p.planner_run_id), spec=MonitoringPlan.model_validate(p.spec) if p.spec else None,
                        error=p.error, created_at=p.created_at, approved_at=p.approved_at)


async def _plan(s: AsyncSession, ws: Workspace, pid: uuid.UUID) -> MonitoringPolicy:
    p = await s.get(MonitoringPolicy, pid)
    if p is None or p.workspace_id != ws.id:
        raise HTTPException(status_code=404, detail="Plan not found")
    return p


@router.post("", response_model=S.PlanDetail)
async def create_plan(body: S.PlanCreate, ws: Workspace = Depends(get_workspace), s: AsyncSession = Depends(session),
                      who: Principal = Depends(current)):
    ws = await s.merge(ws)
    in_flight = (await s.execute(select(MonitoringPolicy).where(
        MonitoringPolicy.workspace_id == ws.id, MonitoringPolicy.status == "planning"))).scalar_one_or_none()
    if in_flight is not None:
        raise HTTPException(status_code=409, detail="A plan is already being prepared for this workspace")
    version = ((await s.execute(select(func.max(MonitoringPolicy.version)).where(
        MonitoringPolicy.workspace_id == ws.id))).scalar_one_or_none() or 0) + 1
    policy = MonitoringPolicy(id=uuid.uuid4(), workspace_id=ws.id, version=version, status="planning",
                              request_text=body.request_text.strip(), created_by=who.user.id)
    s.add(policy)
    await s.flush()
    await enqueue(s, "plan_monitoring", {"policy_id": str(policy.id)}, workspace_id=ws.id,
                  priority=PRIORITY_INTERACTIVE, dedupe_key=f"plan:{policy.id}", max_attempts=1)
    if ws.status in ("setup",):
        ws.status = "planning"
    return plan_out(policy)


@router.get("/{pid}", response_model=S.PlanDetail)
async def get_plan(pid: uuid.UUID, ws: Workspace = Depends(get_workspace), s: AsyncSession = Depends(session)):
    return plan_out(await _plan(s, ws, pid))


@router.put("/{pid}/spec", response_model=S.PlanDetail)
async def put_spec(pid: uuid.UUID, body: S.PlanSpecIn, ws: Workspace = Depends(get_workspace),
                   s: AsyncSession = Depends(session)):
    p = await _plan(s, ws, pid)
    if p.status != "pending_approval":
        raise HTTPException(status_code=409, detail=f"Plan is {p.status}; only plans awaiting approval can be edited")
    p.spec = body.spec.model_dump(mode="json")
    return plan_out(p)


@router.post("/{pid}/approve", response_model=S.ApproveResult)
async def approve(pid: uuid.UUID, body: S.ApproveIn | None = None, ws: Workspace = Depends(get_workspace),
                  s: AsyncSession = Depends(session), who: Principal = Depends(current)):
    p = await _plan(s, ws, pid)
    if p.status != "pending_approval":
        raise HTTPException(status_code=409, detail=f"Plan is {p.status}; only plans awaiting approval can be approved")
    spec = body.spec if body and body.spec else (MonitoringPlan.model_validate(p.spec) if p.spec else None)
    if spec is None or not any(src.enabled for src in spec.sources):
        raise HTTPException(status_code=422, detail="Enable at least one source before approving")
    result = await activate_plan(s, policy=p, plan=spec, user_id=who.user.id)
    return S.ApproveResult(**result)


@router.post("/{pid}/reject", response_model=S.PlanDetail)
async def reject(pid: uuid.UUID, ws: Workspace = Depends(get_workspace), s: AsyncSession = Depends(session)):
    p = await _plan(s, ws, pid)
    if p.status not in ("pending_approval", "failed"):
        raise HTTPException(status_code=409, detail=f"Plan is {p.status}")
    p.status = "rejected"
    ws = await s.merge(ws)
    if ws.status == "awaiting_approval":
        active = (await s.execute(select(MonitoringPolicy).where(MonitoringPolicy.workspace_id == ws.id,
                                                                 MonitoringPolicy.status == "active"))).first()
        ws.status = "monitoring" if active else "setup"
    return plan_out(p)
