"""Monitoring configuration: active policy, sources (check now), filtered changes, learned rules."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from signallens.api import schemas as S
from signallens.api.deps import get_workspace, session
from signallens.db.base import utcnow
from signallens.db.models import Entity, Event, LearnedRule, Source, SourceCheck, SourceSnapshot, Workspace
from signallens.jobs.queue import PRIORITY_INTERACTIVE, enqueue
from signallens.plan import MonitoringPlan
from signallens.store.world import active_policy, effective_policy

router = APIRouter(prefix="/workspaces/{wid}", tags=["monitoring"])


@router.get("/policy", response_model=S.PolicyView)
async def policy(ws: Workspace = Depends(get_workspace), s: AsyncSession = Depends(session)):
    p = await active_policy(s, ws.id)
    if p is None or not p.spec:
        raise HTTPException(status_code=404, detail="No active monitoring plan yet")
    eff = await effective_policy(s, ws.id)
    spec = MonitoringPlan.model_validate(p.spec)
    return S.PolicyView(
        id=str(p.id), version=p.version, status=p.status, approved_at=p.approved_at, request_text=p.request_text,
        summary=spec.summary,
        areas=[S.PolicyArea(key=a.key, label=a.label, importance=a.importance,
                            effective_importance=a.effective_importance, threshold=a.threshold, route_to=a.route_to)
               for a in eff.areas.values()],
        spec=spec,
    )


async def _source_view(s: AsyncSession, src: Source, names: dict[uuid.UUID, str]) -> S.SourceView:
    snaps = (await s.execute(select(func.count(SourceSnapshot.id)).where(SourceSnapshot.source_id == src.id))).scalar_one()
    return S.SourceView(
        id=str(src.id), kind=src.kind, url=src.url, query=src.query,
        entity=S.EntityRef(id=str(src.entity_id), name=names.get(src.entity_id, "")) if src.entity_id else None,
        areas=list(src.areas or []), authority=src.authority, priority=src.priority,
        check_every_hours=round(src.check_every_minutes / 60, 2),
        current_interval_hours=round(src.current_interval_minutes / 60, 2),
        next_check_at=src.next_check_at, last_checked_at=src.last_checked_at, last_changed_at=src.last_changed_at,
        last_outcome=src.last_outcome, consecutive_failures=src.consecutive_failures, active=src.active,
        reason=src.reason or "", snapshots=snaps, backfill=src.backfill,
    )


async def _names(s: AsyncSession, ws_id: uuid.UUID) -> dict[uuid.UUID, str]:
    return dict((await s.execute(select(Entity.id, Entity.name).where(Entity.workspace_id == ws_id))).all())


async def _source(s: AsyncSession, ws: Workspace, sid_: uuid.UUID) -> Source:
    src = await s.get(Source, sid_)
    if src is None or src.workspace_id != ws.id:
        raise HTTPException(status_code=404, detail="Source not found")
    return src


@router.get("/sources", response_model=list[S.SourceView])
async def sources(ws: Workspace = Depends(get_workspace), s: AsyncSession = Depends(session)):
    rows = (await s.execute(select(Source).where(Source.workspace_id == ws.id)
                            .order_by(Source.active.desc(), Source.kind, Source.created_at))).scalars().all()
    names = await _names(s, ws.id)
    return [await _source_view(s, src, names) for src in rows]


@router.patch("/sources/{sid}", response_model=S.SourceView)
async def patch_source(sid: uuid.UUID, body: S.SourcePatch, ws: Workspace = Depends(get_workspace),
                       s: AsyncSession = Depends(session)):
    src = await _source(s, ws, sid)
    if body.active is not None:
        src.active = body.active
    if body.check_every_hours is not None:
        src.check_every_minutes = int(round(body.check_every_hours * 60))
        src.current_interval_minutes = src.check_every_minutes
        src.next_check_at = min(src.next_check_at or utcnow(), utcnow())
    if body.priority is not None:
        src.priority = body.priority
    return await _source_view(s, src, await _names(s, ws.id))


@router.post("/sources/{sid}/check", response_model=S.JobRef)
async def check_now(sid: uuid.UUID, ws: Workspace = Depends(get_workspace), s: AsyncSession = Depends(session)):
    src = await _source(s, ws, sid)
    kind = "check_source" if src.baselined else "baseline_source"
    job_id = await enqueue(s, kind, {"source_id": str(src.id)}, workspace_id=ws.id, priority=PRIORITY_INTERACTIVE,
                           dedupe_key=f"{'check' if src.baselined else 'baseline'}:{src.id}")
    if job_id is None:
        raise HTTPException(status_code=409, detail="A check for this source is already queued or running")
    return S.JobRef(job_id=str(job_id))


@router.get("/sources/{sid}/checks", response_model=list[S.SourceCheckOut])
async def checks(sid: uuid.UUID, limit: int = 20, ws: Workspace = Depends(get_workspace),
                 s: AsyncSession = Depends(session)):
    src = await _source(s, ws, sid)
    rows = (await s.execute(select(SourceCheck).where(SourceCheck.source_id == src.id)
                            .order_by(SourceCheck.started_at.desc()).limit(max(1, min(limit, 100))))).scalars()
    return [S.SourceCheckOut(id=str(c.id), started_at=c.started_at, finished_at=c.finished_at, outcome=c.outcome,
                             http_status=c.http_status, new_items=c.new_items, changes=c.changes, error=c.error)
            for c in rows]


@router.get("/filtered", response_model=list[S.FilteredChange])
async def filtered(limit: int = 50, ws: Workspace = Depends(get_workspace), s: AsyncSession = Depends(session)):
    rows = (await s.execute(select(Event).where(Event.workspace_id == ws.id, Event.status == "filtered")
                            .order_by(Event.detected_at.desc()).limit(max(1, min(limit, 200))))).scalars().all()
    names = await _names(s, ws.id)
    urls = dict((await s.execute(select(Source.id, Source.url).where(Source.workspace_id == ws.id))).all())
    return [S.FilteredChange(
        id=str(e.id), title=e.title, area=e.area,
        entity=S.EntityRef(id=str(e.entity_id), name=names.get(e.entity_id, "")) if e.entity_id else None,
        detected_at=e.detected_at, materiality=e.materiality, filter_reason=e.filter_reason or "",
        detection_source=e.detection_source, source_url=urls.get(e.source_id), tier=e.filter_tier or 0,
    ) for e in rows]


def _rule(rule: LearnedRule) -> S.LearnedRuleOut:
    return S.LearnedRuleOut(id=str(rule.id), kind=rule.kind, explanation=rule.explanation,
                            scope={k: str(v) for k, v in (rule.scope or {}).items()},
                            effect={k: str(v) for k, v in (rule.effect or {}).items()},
                            evidence_count=rule.evidence_count, active=rule.active, created_at=rule.created_at,
                            revoked_at=rule.revoked_at)


@router.get("/learned-rules", response_model=list[S.LearnedRuleOut])
async def learned_rules(ws: Workspace = Depends(get_workspace), s: AsyncSession = Depends(session)):
    rows = (await s.execute(select(LearnedRule).where(LearnedRule.workspace_id == ws.id)
                            .order_by(LearnedRule.active.desc(), LearnedRule.created_at.desc()))).scalars()
    return [_rule(r) for r in rows]


@router.delete("/learned-rules/{rule_id}", response_model=S.LearnedRuleOut)
async def revoke_rule(rule_id: uuid.UUID, ws: Workspace = Depends(get_workspace), s: AsyncSession = Depends(session)):
    rule = await s.get(LearnedRule, rule_id)
    if rule is None or rule.workspace_id != ws.id:
        raise HTTPException(status_code=404, detail="Rule not found")
    rule.active, rule.revoked_at = False, utcnow()
    return _rule(rule)
