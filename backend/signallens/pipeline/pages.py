"""Page change processing, shared by live monitoring and history backfill.

For one (previous → new) pair of snapshots of an official page:

1. **Tracked values** (tier 1): re-read the facts linked to this page. A changed value is
   always material — it becomes an event with a verified quote from the page.
2. **Text diff** (tiers 0/1): block-level diff; hunks that only change volatile tokens
   (dates, ©, counters) or whitespace are dropped as noise.
3. **Materiality** (tier 2): the fast model classifies the remaining hunks against the
   effective policy. Below-threshold changes are kept as *filtered* events (visible in
   "what we ignored and why"); material ones become candidates for investigation.

The same code runs over archived captures during backfill, where resulting events are
marked historical and never notify anyone (C5, C18).
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from signallens.agents.analysts import AttributeSpec, assess_page_changes, extract_attributes
from signallens.agents.schemas import ExtractedValueOut
from signallens.db.models import Document, Entity, Event, Fact, Source, SourceSnapshot, StateVersion
from signallens.db.session import transaction
from signallens.domain.diffing import DiffHunk, PageDiff, diff_lines, drop_noise_hunks, render_diff
from signallens.domain.evidence import classify_source
from signallens.domain.policy import EffectivePolicy
from signallens.domain.values import equivalent
from signallens.pipeline.events import create_event
from signallens.runtime.core import RunContext
from signallens.store.documents import block_lines
from signallens.store.evidence import add_evidence, refresh_status
from signallens.store.world import record_value, version_at
from signallens.util.text import quote_in_text

log = logging.getLogger(__name__)


@dataclass
class ChangeOutcome:
    changes: int = 0  # hunks or values that changed (after noise filtering)
    material: list[uuid.UUID] = field(default_factory=list)  # event ids worth investigating/analysing
    filtered: int = 0
    noise_only: bool = False


async def last_ok_snapshot(session: AsyncSession, source_id: uuid.UUID, *, before: datetime | None = None,
                           origin: str | None = None) -> tuple[SourceSnapshot, Document] | None:
    q = (select(SourceSnapshot, Document).join(Document, Document.id == SourceSnapshot.document_id)
         .where(SourceSnapshot.source_id == source_id, SourceSnapshot.quality == "ok"))
    if before is not None:
        q = q.where(SourceSnapshot.observed_at < before)
    if origin is not None:
        q = q.where(SourceSnapshot.origin == origin)
    row = (await session.execute(q.order_by(SourceSnapshot.observed_at.desc()).limit(1))).first()
    return (row[0], row[1]) if row else None


async def linked_facts(session: AsyncSession, source: Source) -> list[Fact]:
    facts = (await session.execute(select(Fact).where(Fact.workspace_id == source.workspace_id,
                                                      Fact.active.is_(True)))).scalars().all()
    explicit = [f for f in facts if source.plan_ref and source.plan_ref in (f.source_refs or [])]
    if explicit:
        return explicit
    return [f for f in facts if not f.source_refs and f.entity_id == source.entity_id and f.area in (source.areas or [])]


async def previous_versions(facts: list[Fact], at: datetime, session: AsyncSession) -> dict:
    return {f.id: await version_at(session, f.id, at) for f in facts}


async def read_values(
    ctx: RunContext, *, facts: list[Fact], previous: dict, doc: Document, url: str,
    when_label: str | None = None,
) -> list[tuple[Fact, ExtractedValueOut, StateVersion | None, bool]]:
    """Extract linked facts from a document; keep only values whose quote is really on the page.

    Called outside any database transaction: it waits on a model.
    """
    specs = [AttributeSpec(key=f.key, label=f.label, hint=f.hint, value_type=f.value_type,
                           previous_display=previous[f.id].value_display if previous[f.id] else None) for f in facts]
    values = await extract_attributes(ctx, url=url, page_text=doc.text, attributes=specs, when=when_label)
    by_key = {f.key: f for f in facts}
    readings = []
    for v in values:
        fact = by_key.get(v.key)
        if fact is None or not v.found or not v.value_display:
            continue
        if not v.quote or not quote_in_text(v.quote, doc.text):
            await ctx.step("guardrail", f"Discarded value for {fact.label}: quote not found on the page", name="quote_check",
                           input={"quote": v.quote, "value": v.value_display})
            continue
        prev = previous[fact.id]
        changed = prev is None or not equivalent(
            prev.value, display=v.value_display, number=v.number, unit=v.unit, conditions=v.conditions,
            same_as_previous=v.same_as_previous,
        )
        readings.append((fact, v, prev, changed))
    return readings


def _hunks_text(hunks: list[DiffHunk]) -> str:
    return render_diff(PageDiff(hunks=hunks, lines_added=0, lines_removed=0, old_line_count=0, new_line_count=0),
                       max_chars=3000)


def _quote_from_hunks(hunks: list[DiffHunk], text: str) -> str | None:
    """A verifiable quote from the new page for a diff-based change (after-lines, else context)."""
    for h in hunks:
        for line in [*h.after, *h.context_after, *h.context_before]:
            if len(line.strip()) >= 3 and quote_in_text(line, text):
                return line.strip()
    return None


async def process_page_change(
    ctx: RunContext,
    *,
    source: Source,
    entity: Entity | None,
    policy: EffectivePolicy,
    prev_doc: Document,
    new_doc: Document,
    observed_at: datetime,
    prev_observed_at: datetime | None,
    historical: bool,
    regulator_domains: list[str],
) -> ChangeOutcome:
    services = ctx.services
    outcome = ChangeOutcome()
    status_material = "historical" if historical else "candidate"
    detection = "backfill" if historical else "attribute"
    url = source.url or ""
    entity_name = entity.name if entity else "the monitored entity"
    domains = list(entity.official_domains) if entity else []
    source_class = classify_source(url, entity_domains=domains, regulator_domains=regulator_domains,
                                   distrusted_publishers=policy.distrusted_publishers)
    when_label = observed_at.date().isoformat()
    between = {"between": [prev_observed_at.isoformat() if prev_observed_at else None, observed_at.isoformat()]}
    llm_ready = services.llm is not None
    attr_titles: list[str] = []

    # 1) Tracked values: changes always pass the gate (tier 1).
    async with services.session_factory() as s:
        facts = await linked_facts(s, source)
        previous = await previous_versions(facts, observed_at, s)
    readings = await read_values(ctx, facts=facts, previous=previous, doc=new_doc, url=url,
                                 when_label=when_label) if (facts and llm_ready) else []
    async with transaction(services.session_factory) as s:
        for detached, v, prev, changed in readings:
            if not changed:
                continue
            fact = await s.get(Fact, detached.id)
            version = await record_value(
                s, fact=fact, display=v.value_display, number=v.number, unit=v.unit, conditions=v.conditions,
                observed_at=observed_at, observed_via="archive" if historical else "live",
                evidence_status="confirmed" if source_class == "primary" else "single_source",
                quote=v.quote, source_id=source.id, document_id=new_doc.id,
            )
            if prev is None:
                continue  # first sighting of this value: part of the baseline, not a change
            title = f"{entity_name}: {fact.label} changed"
            event, claim = await create_event(
                s, workspace_id=source.workspace_id, title=title,
                claim=f"{entity_name}'s {fact.label.lower()} changed from “{prev.value_display}” to "
                      f"“{v.value_display}”.",
                status=status_material, area=fact.area,
                event_type="pricing" if fact.area == "pricing" else "value_change",
                detection_source=detection, entity_id=entity.id if entity else None, fact_id=fact.id,
                source_id=source.id, summary=f"{fact.label}: {prev.value_display} → {v.value_display}",
                before=prev.value_display, after=v.value_display, detected_at=observed_at if historical else None,
                document_id=new_doc.id, cluster_key=f"attr:{fact.id}:{version.value_key}", materiality="high",
                materiality_reason="A tracked value changed; tracked values always pass the materiality gate.",
                is_historical=historical, details=between if historical else {},
            )
            version.event_id = event.id
            await add_evidence(
                s, workspace_id=source.workspace_id, claim_id=claim.id, url=url if not historical else _archive_url(new_doc),
                quote=v.quote, stance="supports", source_class=source_class, publisher=new_doc.publisher,
                quote_verified=True, title=new_doc.title, document_id=new_doc.id,
                published_at=observed_at if historical else None, is_archive=historical,
            )
            await refresh_status(s, claim_id=claim.id, event_id=event.id, distrusted=policy.distrusted_publishers)
            outcome.material.append(event.id)
            outcome.changes += 1
            attr_titles.append(f"{fact.label}: {prev.value_display} -> {v.value_display}")

    # 2) Text diff with deterministic noise removal (tiers 0/1).
    diff = diff_lines(block_lines(prev_doc), block_lines(new_doc))
    kept, dropped = drop_noise_hunks(diff)
    if kept.is_empty:
        if dropped and not historical and not outcome.changes:
            async with transaction(services.session_factory) as s:
                await create_event(
                    s, workspace_id=source.workspace_id, title=f"Only volatile or cosmetic changes on {url}",
                    claim="No material change.", status="filtered", area=(source.areas or ["general"])[0],
                    event_type="content_change", detection_source="page_diff", entity_id=entity.id if entity else None,
                    source_id=source.id, document_id=new_doc.id, materiality="none", filter_tier=1,
                    filter_reason="; ".join(sorted(set(dropped)))[:500],
                )
            outcome.filtered += 1
            outcome.noise_only = True
        return outcome

    outcome.changes += len(kept.hunks)
    if not llm_ready:
        return outcome

    # 3) Materiality on what is left (tier 2).
    ma = await assess_page_changes(
        ctx, url=url, entity_name=entity_name, diff_text=render_diff(kept, max_chars=7000),
        policy_text=policy.describe_for_prompt(), already_detected=attr_titles,
        when=f"between {prev_observed_at.date().isoformat() if prev_observed_at else 'earlier'} and {when_label}",
    )
    async with transaction(services.session_factory) as s:
        for change in ma.changes:
            hunks = [kept.hunks[i - 1] for i in change.hunk_ids if 1 <= i <= len(kept.hunks)] or kept.hunks[:1]
            excerpt = _hunks_text(hunks)
            area = change.area if change.area in policy.areas else (source.areas or ["general"])[0]
            material = policy.is_material(change.materiality, area, change.event_type)
            if not material and historical:
                continue  # history keeps only what mattered
            threshold = policy.threshold_for(area, change.event_type)
            event, claim = await create_event(
                s, workspace_id=source.workspace_id, title=f"{entity_name}: {change.title}",
                claim=change.summary, status=status_material if material else "filtered", area=area,
                event_type=change.event_type if change.event_type else "content_change",
                detection_source="backfill" if historical else "page_diff",
                entity_id=entity.id if entity else None, source_id=source.id, summary=change.summary,
                before=change.before, after=change.after, detected_at=observed_at if historical else None,
                document_id=new_doc.id, diff_excerpt=excerpt, materiality=change.materiality,
                materiality_reason=change.reason, filter_tier=None if material else 2,
                filter_reason=None if material else (
                    f"{change.reason} (materiality {change.materiality}; alert threshold for "
                    f"{policy.area(area).label} is {threshold})"),
                cluster_key=None, is_historical=historical, details=between if historical else {},
            )
            if material:
                quote = _quote_from_hunks(hunks, new_doc.text)
                if quote:
                    await add_evidence(
                        s, workspace_id=source.workspace_id, claim_id=claim.id,
                        url=url if not historical else _archive_url(new_doc), quote=quote, stance="supports",
                        source_class=source_class, publisher=new_doc.publisher, quote_verified=True,
                        title=new_doc.title, document_id=new_doc.id, is_archive=historical,
                        published_at=observed_at if historical else None,
                        note="Text as it appears on the page after the change.",
                    )
                    await refresh_status(s, claim_id=claim.id, event_id=event.id,
                                         distrusted=policy.distrusted_publishers)
                outcome.material.append(event.id)
            else:
                outcome.filtered += 1
        if ma.noise_hunk_ids and not historical:
            noise = [kept.hunks[i - 1] for i in ma.noise_hunk_ids if 1 <= i <= len(kept.hunks)]
            if noise:
                await create_event(
                    s, workspace_id=source.workspace_id, title=f"{len(noise)} cosmetic change(s) on {url}",
                    claim="No material change.", status="filtered", area=(source.areas or ["general"])[0],
                    event_type="content_change", detection_source="page_diff", entity_id=entity.id if entity else None,
                    source_id=source.id, document_id=new_doc.id, diff_excerpt=_hunks_text(noise), materiality="none",
                    filter_tier=2, filter_reason=ma.noise_reason or "Judged as noise by the materiality filter.",
                )
                outcome.filtered += 1
    return outcome


def _archive_url(doc: Document) -> str:
    return doc.url


async def event_ids_with_status(session: AsyncSession, ids: list[uuid.UUID], status: str) -> list[uuid.UUID]:
    if not ids:
        return []
    rows = await session.execute(select(Event.id).where(Event.id.in_(ids), Event.status == status))
    return [r[0] for r in rows]
