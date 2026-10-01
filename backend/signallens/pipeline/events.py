"""Creating events, and merging new reports of an existing event (clustering, C3)."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from signallens.db.base import utcnow
from signallens.db.models import Claim, Event
from signallens.domain.clustering import CLUSTER_WINDOW_DAYS, titles_similar

OPEN_STATUSES = ("candidate", "investigating", "analyzing", "published", "historical")


async def create_event(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    title: str,
    claim: str,
    status: str,
    area: str,
    event_type: str,
    detection_source: str,
    entity_id: uuid.UUID | None = None,
    fact_id: uuid.UUID | None = None,
    source_id: uuid.UUID | None = None,
    summary: str = "",
    before: str | None = None,
    after: str | None = None,
    detected_at: datetime | None = None,
    occurred_at: datetime | None = None,
    snapshot_id: uuid.UUID | None = None,
    document_id: uuid.UUID | None = None,
    diff_excerpt: str | None = None,
    cluster_key: str | None = None,
    materiality: str = "none",
    materiality_reason: str | None = None,
    filter_tier: int | None = None,
    filter_reason: str | None = None,
    is_historical: bool = False,
    details: dict[str, Any] | None = None,
) -> tuple[Event, Claim]:
    event = Event(
        id=uuid.uuid4(), workspace_id=workspace_id, entity_id=entity_id, fact_id=fact_id, source_id=source_id,
        area=area, event_type=event_type, title=title[:500], summary=summary, before_display=before,
        after_display=after, detected_at=detected_at or utcnow(), occurred_at=occurred_at,
        detection_source=detection_source, snapshot_id=snapshot_id, document_id=document_id,
        diff_excerpt=diff_excerpt, cluster_key=cluster_key, status=status, materiality=materiality,
        materiality_reason=materiality_reason, filter_tier=filter_tier, filter_reason=filter_reason,
        is_historical=is_historical, details=details or {},
    )
    session.add(event)
    await session.flush()
    claim_row = Claim(id=uuid.uuid4(), workspace_id=workspace_id, event_id=event.id, entity_id=entity_id,
                      statement=claim or title, claim_type="value" if fact_id else "occurrence")
    session.add(claim_row)
    await session.flush()
    return event, claim_row


async def find_cluster(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    cluster_key: str | None,
    entity_id: uuid.UUID | None,
    event_type: str,
    title: str,
    around: datetime | None = None,
) -> Event | None:
    """An open event that a new item describes, by structured key or near-identical title."""
    ref = around or utcnow()
    lo, hi = ref - timedelta(days=CLUSTER_WINDOW_DAYS), ref + timedelta(days=CLUSTER_WINDOW_DAYS)
    base = select(Event).where(
        Event.workspace_id == workspace_id, Event.status.in_(OPEN_STATUSES),
        Event.detected_at >= lo - timedelta(days=CLUSTER_WINDOW_DAYS), Event.detected_at <= hi,
    )
    if cluster_key:
        hit = (await session.execute(base.where(Event.cluster_key == cluster_key).order_by(Event.detected_at).limit(1))
               ).scalar_one_or_none()
        if hit:
            return hit
    candidates = (await session.execute(
        base.where(Event.entity_id == entity_id, Event.event_type == event_type).order_by(Event.detected_at.desc()).limit(40)
    )).scalars().all()
    for ev in candidates:
        if titles_similar(ev.title, title):
            return ev
    return None
