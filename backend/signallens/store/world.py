"""World-state writes: versioned facts and the effective policy for a workspace."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from signallens.db.models import Entity, Fact, LearnedRule, MonitoringPolicy, StateVersion
from signallens.domain.policy import EffectivePolicy, build_effective_policy
from signallens.domain.values import value_key


async def record_value(
    session: AsyncSession,
    *,
    fact: Fact,
    display: str,
    number: float | None,
    unit: str | None,
    conditions: str | None,
    observed_at: datetime,
    observed_via: str,
    evidence_status: str,
    quote: str | None,
    source_id: uuid.UUID | None = None,
    document_id: uuid.UUID | None = None,
    event_id: uuid.UUID | None = None,
    valid_from: datetime | None = None,
) -> StateVersion:
    """Append a new version; make it current only if it is the newest observation."""
    version = StateVersion(
        id=uuid.uuid4(),
        fact_id=fact.id,
        value={"display": display, "number": number, "unit": unit, "conditions": conditions},
        value_display=display,
        value_key=value_key(display=display, number=number, unit=unit, conditions=conditions),
        valid_from=valid_from,
        observed_at=observed_at,
        observed_via=observed_via,
        source_id=source_id,
        document_id=document_id,
        event_id=event_id,
        evidence_status=evidence_status,
        quote=quote,
    )
    session.add(version)
    await session.flush()
    current = await session.get(StateVersion, fact.current_version_id) if fact.current_version_id else None
    if current is None or observed_at >= current.observed_at:
        fact.current_version_id = version.id
    if fact.first_seen_at is None or observed_at < fact.first_seen_at:
        fact.first_seen_at = observed_at
    fact.last_changed_at = await _last_change(session, fact.id)
    return version


async def _last_change(session: AsyncSession, fact_id: uuid.UUID) -> datetime | None:
    """When the current value first appeared, if the value ever changed (history can arrive out of
    order: a backfill adds older versions after today's baseline)."""
    rows = (await session.execute(
        select(StateVersion.value_key, StateVersion.observed_at).where(StateVersion.fact_id == fact_id)
        .order_by(StateVersion.observed_at)
    )).all()
    if not rows:
        return None
    i, newest = len(rows) - 1, rows[-1].value_key
    while i > 0 and rows[i - 1].value_key == newest:
        i -= 1
    return rows[i].observed_at if i > 0 else None


async def version_at(session: AsyncSession, fact_id: uuid.UUID, when: datetime) -> StateVersion | None:
    """The version that was current at ``when`` (latest observation at or before it)."""
    return (await session.execute(
        select(StateVersion).where(StateVersion.fact_id == fact_id, StateVersion.observed_at <= when)
        .order_by(StateVersion.observed_at.desc()).limit(1)
    )).scalar_one_or_none()


async def history(session: AsyncSession, fact_id: uuid.UUID) -> list[StateVersion]:
    return list((await session.execute(
        select(StateVersion).where(StateVersion.fact_id == fact_id).order_by(StateVersion.observed_at)
    )).scalars())


async def active_policy(session: AsyncSession, workspace_id: uuid.UUID) -> MonitoringPolicy | None:
    return (await session.execute(
        select(MonitoringPolicy).where(MonitoringPolicy.workspace_id == workspace_id,
                                       MonitoringPolicy.status == "active")
        .order_by(MonitoringPolicy.version.desc()).limit(1)
    )).scalar_one_or_none()


async def effective_policy(session: AsyncSession, workspace_id: uuid.UUID) -> EffectivePolicy:
    policy = await active_policy(session, workspace_id)
    rules = (await session.execute(
        select(LearnedRule).where(LearnedRule.workspace_id == workspace_id, LearnedRule.active.is_(True))
        .order_by(LearnedRule.created_at)
    )).scalars().all()
    return build_effective_policy(policy.spec if policy else None, list(rules))


async def entity_domains(session: AsyncSession, workspace_id: uuid.UUID) -> tuple[dict[uuid.UUID, Entity], list[str]]:
    """All entities of a workspace, plus the official domains of its regulators."""
    ents = (await session.execute(select(Entity).where(Entity.workspace_id == workspace_id))).scalars().all()
    by_id = {e.id: e for e in ents}
    regulator_domains = [d for e in ents if e.role == "regulator" or e.kind == "regulator" for d in e.official_domains]
    return by_id, regulator_domains


def entity_brief(e: Entity) -> dict[str, Any]:
    return {"name": e.name, "kind": e.kind, "role": e.role, "aliases": e.aliases, "domains": e.official_domains}
