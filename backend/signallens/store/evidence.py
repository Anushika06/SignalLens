"""Evidence storage and status recomputation (rules live in ``domain.evidence``)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from signallens.db.base import utcnow
from signallens.db.models import Claim, Event, Evidence, IntelligenceReport, Notification
from signallens.domain.evidence import EvidenceAssessment, EvidenceItem, assess
from signallens.util.text import normalize_for_match


async def add_evidence(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    claim_id: uuid.UUID,
    url: str,
    quote: str,
    stance: str,
    source_class: str,
    publisher: str,
    quote_verified: bool,
    title: str | None = None,
    document_id: uuid.UUID | None = None,
    published_at: datetime | None = None,
    is_archive: bool = False,
    added_by: str = "pipeline",
    run_id: uuid.UUID | None = None,
    note: str | None = None,
) -> Evidence | None:
    """Insert evidence unless the same quote from the same URL is already recorded."""
    existing = (await session.execute(
        select(Evidence).where(Evidence.claim_id == claim_id, Evidence.url == url)
    )).scalars().all()
    nq = normalize_for_match(quote)
    for e in existing:
        if normalize_for_match(e.quote) == nq:
            return None
    ev = Evidence(
        id=uuid.uuid4(), workspace_id=workspace_id, claim_id=claim_id, url=url, title=title,
        publisher=publisher, source_class=source_class, is_archive=is_archive, stance=stance,
        quote=quote[:2000], quote_verified=quote_verified, document_id=document_id,
        published_at=published_at, added_by=added_by, run_id=run_id, note=note,
    )
    session.add(ev)
    await session.flush()
    return ev


async def assess_claim(session: AsyncSession, claim_id: uuid.UUID, *, distrusted: set[str]) -> EvidenceAssessment:
    rows = (await session.execute(select(Evidence).where(Evidence.claim_id == claim_id))).scalars().all()
    items = [
        EvidenceItem(source_class=e.source_class, stance=e.stance, publisher=e.publisher, quote=e.quote,
                     quote_verified=e.quote_verified, url=e.url, is_archive=e.is_archive)
        for e in rows
    ]
    return assess(items, distrusted_publishers=distrusted)


async def refresh_status(
    session: AsyncSession, *, claim_id: uuid.UUID, event_id: uuid.UUID, distrusted: set[str]
) -> EvidenceAssessment:
    """Recompute the claim's status and propagate it to the event (and its report, if any).

    Evidence can keep arriving after a card is published (another outlet, a correction).
    Upgrades update the card silently; a downgrade to *conflicting* notifies the card's
    teams again, because people may already have acted on it.
    """
    a = await assess_claim(session, claim_id, distrusted=distrusted)
    await session.execute(update(Claim).where(Claim.id == claim_id).values(evidence_status=a.status))
    await session.execute(update(Event).where(Event.id == event_id).values(evidence_status=a.status))
    report = (await session.execute(select(IntelligenceReport).where(IntelligenceReport.event_id == event_id))
              ).scalar_one_or_none()
    if report is not None:
        became_conflicting = a.status == "conflicting" and report.evidence_status != "conflicting"
        report.evidence_status, report.evidence_summary = a.status, a.summary
        if became_conflicting and not report.is_historical:
            for team_id in report.affected_team_ids or []:
                session.add(Notification(id=uuid.uuid4(), workspace_id=report.workspace_id, report_id=report.id,
                                         team_id=uuid.UUID(team_id), channel="inbox", status="sent",
                                         sent_at=utcnow()))
    return a


async def primary_claim(session: AsyncSession, event_id: uuid.UUID) -> Claim | None:
    return (await session.execute(
        select(Claim).where(Claim.event_id == event_id).order_by(Claim.created_at).limit(1)
    )).scalar_one_or_none()
