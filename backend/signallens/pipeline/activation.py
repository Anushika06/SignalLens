"""Human approval → persistent monitoring configuration.

Approving a plan materialises it: entities (and their relationships), tracked facts and
scheduled sources, then enqueues a baseline for every new source and a history backfill
for official pages. All of it happens in one transaction with the approval itself.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from signallens.db.base import utcnow
from signallens.db.models import Entity, EntityRelationship, Fact, MonitoringPolicy, Source, Workspace
from signallens.jobs.queue import PRIORITY_INTERACTIVE, PRIORITY_PIPELINE, enqueue
from signallens.plan import MonitoringPlan
from signallens.util.urls import host_of

ROLE_PREDICATES = {"competitor": "competes_with", "regulator": "regulated_by", "partner": "partners_with"}


def name_key(name: str) -> str:
    return " ".join(name.lower().split())[:300]


async def upsert_entity(
    session: AsyncSession, workspace_id: uuid.UUID, *, name: str, kind: str, role: str,
    aliases: list[str] | None = None, official_domains: list[str] | None = None, description: str = "",
    plan_ref: str | None = None,
) -> Entity:
    key = name_key(name)
    entity = (await session.execute(
        select(Entity).where(Entity.workspace_id == workspace_id, Entity.name_key == key)
    )).scalar_one_or_none()
    if entity is None:
        entity = Entity(id=uuid.uuid4(), workspace_id=workspace_id, name=name.strip(), name_key=key)
        session.add(entity)
    entity.kind, entity.role = kind, role
    entity.aliases = sorted(set((entity.aliases or []) + (aliases or [])))
    entity.official_domains = sorted(set((entity.official_domains or []) + (official_domains or [])))
    entity.description = description or entity.description
    entity.plan_ref = plan_ref or entity.plan_ref
    await session.flush()
    return entity


async def relate(session: AsyncSession, workspace_id: uuid.UUID, subject: Entity, predicate: str, obj: Entity,
                 *, event_id: uuid.UUID | None = None, properties: dict[str, Any] | None = None) -> None:
    rel = (await session.execute(select(EntityRelationship).where(
        EntityRelationship.subject_id == subject.id, EntityRelationship.predicate == predicate,
        EntityRelationship.object_id == obj.id,
    ))).scalar_one_or_none()
    if rel is None:
        session.add(EntityRelationship(id=uuid.uuid4(), workspace_id=workspace_id, subject_id=subject.id,
                                       predicate=predicate, object_id=obj.id, event_id=event_id,
                                       properties=properties or {}))
    else:
        rel.last_seen_at = utcnow()
    await session.flush()


async def activate_plan(session: AsyncSession, *, policy: MonitoringPolicy, plan: MonitoringPlan,
                        user_id: uuid.UUID | None) -> dict[str, Any]:
    ws = await session.get(Workspace, policy.workspace_id)
    wid = ws.id

    previous = (await session.execute(select(MonitoringPolicy).where(
        MonitoringPolicy.workspace_id == wid, MonitoringPolicy.status == "active", MonitoringPolicy.id != policy.id,
    ))).scalars().all()
    for p in previous:
        p.status = "superseded"
    policy.spec = plan.model_dump(mode="json")
    policy.status, policy.approved_at, policy.approved_by = "active", utcnow(), user_id

    # Entities and relationships
    by_ref: dict[str, Entity] = {}
    for pe in plan.entities:
        if pe.enabled:
            by_ref[pe.ref] = await upsert_entity(
                session, wid, name=pe.name, kind=pe.kind, role=pe.role, aliases=pe.aliases,
                official_domains=pe.official_domains, description=pe.description, plan_ref=pe.ref,
            )
    subjects = [by_ref[e.ref] for e in plan.entities if e.enabled and e.role == "subject" and e.ref in by_ref]
    for pe in plan.entities:
        if pe.enabled and pe.role in ROLE_PREDICATES and pe.ref in by_ref:
            for subj in subjects:
                await relate(session, wid, subj, ROLE_PREDICATES[pe.role], by_ref[pe.ref])
    profile = ws.profile or {}
    if (profile.get("company_name") or "").strip():
        website = profile.get("website") or ""
        us = await upsert_entity(
            session, wid, name=profile["company_name"], kind="company", role="us",
            official_domains=[host_of(website).removeprefix("www.")] if website else [],
            description=profile.get("description") or "",
        )
        for subj in subjects:
            if subj.id != us.id:
                await relate(session, wid, us, "monitors", subj)

    # Tracked facts
    wanted_keys: set[tuple[uuid.UUID, str]] = set()
    for pa in plan.attributes:
        entity = by_ref.get(pa.entity_ref) or (subjects[0] if subjects else None)
        if not pa.enabled or entity is None:
            continue
        wanted_keys.add((entity.id, pa.key))
        fact = (await session.execute(select(Fact).where(Fact.entity_id == entity.id, Fact.key == pa.key))
                ).scalar_one_or_none()
        if fact is None:
            fact = Fact(id=uuid.uuid4(), workspace_id=wid, entity_id=entity.id, key=pa.key, label=pa.label,
                        area=pa.area)
            session.add(fact)
        fact.label, fact.area, fact.value_type, fact.hint = pa.label, pa.area, pa.value_type, pa.hint
        fact.source_refs, fact.active = list(pa.source_refs), True
    for fact in (await session.execute(select(Fact).where(Fact.workspace_id == wid))).scalars():
        if (fact.entity_id, fact.key) not in wanted_keys:
            fact.active = False

    # Sources
    existing = {(s.kind, s.url or s.query): s for s in
                (await session.execute(select(Source).where(Source.workspace_id == wid))).scalars()}
    keep: set[uuid.UUID] = set()
    created = 0
    for ps in plan.sources:
        if not ps.enabled:
            continue
        ident = (ps.kind, ps.url if ps.kind == "page" else ps.query)
        src = existing.get(ident)
        if src is None:
            src = Source(id=uuid.uuid4(), workspace_id=wid, kind=ps.kind, url=ps.url, query=ps.query)
            session.add(src)
            created += 1
        minutes = int(round(ps.check_every_hours * 60))
        entity = by_ref.get(ps.entity_ref) or (subjects[0] if subjects else None)
        src.policy_id, src.entity_id = policy.id, entity.id if entity else None
        src.areas, src.authority, src.priority = list(ps.areas), ps.authority, ps.priority
        src.check_every_minutes = minutes
        src.current_interval_minutes = src.current_interval_minutes if src.baselined else minutes
        src.backfill, src.reason, src.plan_ref, src.active = ps.backfill, ps.reason, ps.ref, True
        keep.add(src.id)
    for src in existing.values():
        if src.id not in keep:
            src.active = False
    await session.flush()

    # Baseline and backfill jobs, in the same transaction
    jobs = 0
    for src in (await session.execute(select(Source).where(Source.workspace_id == wid, Source.active.is_(True)))).scalars():
        if not src.baselined:
            if await enqueue(session, "baseline_source", {"source_id": str(src.id)}, workspace_id=wid,
                             priority=PRIORITY_INTERACTIVE, dedupe_key=f"baseline:{src.id}"):
                jobs += 1
            if src.kind == "page" and src.backfill and not (src.config or {}).get("backfilled"):
                if await enqueue(session, "backfill_source", {"source_id": str(src.id)}, workspace_id=wid,
                                 priority=PRIORITY_PIPELINE, dedupe_key=f"backfill:{src.id}"):
                    jobs += 1
    ws.status = "baselining" if jobs else "monitoring"
    return {"policy_id": str(policy.id), "status": "active", "sources_created": created, "jobs_enqueued": jobs}
