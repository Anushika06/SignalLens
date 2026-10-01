"""The world state: entities, their tracked facts with full history, relationships, timeline."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from signallens.api import schemas as S
from signallens.api.deps import get_workspace, session
from signallens.api.views import version_outs
from signallens.db.models import (
    Entity,
    EntityRelationship,
    Event,
    Fact,
    IntelligenceReport,
    StateVersion,
    Workspace,
)

router = APIRouter(prefix="/workspaces/{wid}", tags=["world"])


async def _entity_summary(s: AsyncSession, e: Entity) -> S.EntitySummary:
    facts = (await s.execute(select(func.count(Fact.id)).where(Fact.entity_id == e.id, Fact.active.is_(True)))).scalar_one()
    reports = (await s.execute(select(func.count(IntelligenceReport.id)).where(IntelligenceReport.entity_id == e.id))).scalar_one()
    last = (await s.execute(select(func.max(Event.detected_at)).where(
        Event.entity_id == e.id, Event.status.in_(("published", "historical"))))).scalar_one_or_none()
    return S.EntitySummary(id=str(e.id), name=e.name, kind=e.kind, role=e.role, aliases=list(e.aliases or []),
                           official_domains=list(e.official_domains or []), description=e.description or "",
                           facts_count=facts, reports_count=reports, last_change_at=last)


async def _fact_summary(s: AsyncSession, f: Fact) -> S.FactSummary:
    current = await s.get(StateVersion, f.current_version_id) if f.current_version_id else None
    count = (await s.execute(select(func.count(StateVersion.id)).where(StateVersion.fact_id == f.id))).scalar_one()
    return S.FactSummary(id=str(f.id), key=f.key, label=f.label, area=f.area, value_type=f.value_type,
                         current=(await version_outs(s, [current]))[0] if current else None, versions=count,
                         last_changed_at=f.last_changed_at)


ROLE_ORDER = {"subject": 0, "us": 1, "competitor": 2, "regulator": 3, "partner": 4, "related": 5}


@router.get("/entities", response_model=list[S.EntitySummary])
async def entities(ws: Workspace = Depends(get_workspace), s: AsyncSession = Depends(session)):
    rows = (await s.execute(select(Entity).where(Entity.workspace_id == ws.id))).scalars().all()
    rows = sorted(rows, key=lambda e: (ROLE_ORDER.get(e.role, 9), e.name.lower()))
    return [await _entity_summary(s, e) for e in rows]


@router.get("/entities/{eid}", response_model=S.EntityDetail)
async def entity_detail(eid: uuid.UUID, ws: Workspace = Depends(get_workspace), s: AsyncSession = Depends(session)):
    e = await s.get(Entity, eid)
    if e is None or e.workspace_id != ws.id:
        raise HTTPException(status_code=404, detail="Entity not found")
    facts = (await s.execute(select(Fact).where(Fact.entity_id == e.id, Fact.active.is_(True))
                             .order_by(Fact.area, Fact.label))).scalars().all()
    rels = (await s.execute(select(EntityRelationship).where(
        or_(EntityRelationship.subject_id == e.id, EntityRelationship.object_id == e.id)))).scalars().all()
    others = {x.id: x for x in (await s.execute(select(Entity).where(Entity.id.in_(
        {r.object_id if r.subject_id == e.id else r.subject_id for r in rels})))).scalars()} if rels else {}
    events = (await s.execute(select(Event, IntelligenceReport).outerjoin(
        IntelligenceReport, IntelligenceReport.event_id == Event.id).where(
        Event.entity_id == e.id, Event.status.in_(("published", "historical")))
        .order_by(Event.detected_at.desc()).limit(100))).all()
    relationships = []
    for r in rels:
        other_id = r.object_id if r.subject_id == e.id else r.subject_id
        other = others.get(other_id)
        if other is None:
            continue
        relationships.append(S.RelationshipOut(
            id=str(r.id), predicate=r.predicate, direction="out" if r.subject_id == e.id else "in",
            other=S.EntityKindRef(id=str(other.id), name=other.name, kind=other.kind),
            first_seen_at=r.first_seen_at, last_seen_at=r.last_seen_at))
    return S.EntityDetail(
        entity=await _entity_summary(s, e),
        facts=[await _fact_summary(s, f) for f in facts],
        relationships=relationships,
        timeline=[S.TimelineItem(
            report_id=str(rep.id) if rep else None, event_id=str(ev.id), title=rep.title if rep else ev.title,
            area=ev.area, event_type=ev.event_type, severity=rep.severity if rep else ev.severity,
            evidence_status=ev.evidence_status, occurred_at=ev.occurred_at, detected_at=ev.detected_at,
            is_historical=ev.is_historical) for ev, rep in events],
    )


@router.get("/facts/{fid}", response_model=S.FactDetail)
async def fact_detail(fid: uuid.UUID, ws: Workspace = Depends(get_workspace), s: AsyncSession = Depends(session)):
    f = await s.get(Fact, fid)
    if f is None or f.workspace_id != ws.id:
        raise HTTPException(status_code=404, detail="Fact not found")
    e = await s.get(Entity, f.entity_id)
    versions = (await s.execute(select(StateVersion).where(StateVersion.fact_id == f.id)
                                .order_by(StateVersion.observed_at))).scalars().all()
    return S.FactDetail(fact=await _fact_summary(s, f), entity=S.EntityRef(id=str(e.id), name=e.name),
                        versions=await version_outs(s, list(versions)))
