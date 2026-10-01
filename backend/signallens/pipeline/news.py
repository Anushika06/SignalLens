"""Event-stream processing for news sources (spec review C2, C3).

New articles → triage (fast model) → entity resolution → clustering. An article about an
event we already know attaches to it as more evidence (clustering *is* corroboration);
otherwise a new event is created, material ones as candidates for investigation.
"""

from __future__ import annotations

import asyncio
import logging
import re
import uuid
from dataclasses import dataclass, field

from sqlalchemy import select

from signallens.agents.analysts import triage_news
from signallens.agents.schemas import TriageItemOut
from signallens.db.models import Document, Entity, Source
from signallens.db.session import transaction
from signallens.domain.clustering import cluster_key
from signallens.domain.evidence import classify_source
from signallens.domain.levels import EVENT_TYPES
from signallens.domain.policy import EffectivePolicy
from signallens.fetch.extract import extract_result
from signallens.pipeline.common import parse_date, today_str
from signallens.pipeline.events import create_event, find_cluster
from signallens.runtime.core import RunContext
from signallens.search.base import SearchResult
from signallens.store.documents import publisher_of, save_document
from signallens.store.evidence import add_evidence, primary_claim, refresh_status
from signallens.util.text import normalize_for_match, quote_in_text
from signallens.util.urls import normalize_url

log = logging.getLogger(__name__)

MAX_ITEMS_PER_BATCH = 10


@dataclass
class NewsOutcome:
    new_items: int = 0
    relevant: int = 0
    merged: int = 0
    material: list[uuid.UUID] = field(default_factory=list)
    filtered: int = 0


async def unseen(ctx: RunContext, workspace_id: uuid.UUID, results: list[SearchResult]) -> list[SearchResult]:
    urls = {normalize_url(r.url): r for r in results}
    async with ctx.services.session_factory() as s:
        seen = set((await s.execute(
            select(Document.url).where(Document.workspace_id == workspace_id, Document.url.in_(list(urls)))
        )).scalars())
    return [r for u, r in urls.items() if u not in seen]


def resolve_entity(name: str | None, entities: list[Entity], fallback: Entity | None) -> Entity | None:
    if name:
        n = normalize_for_match(name)
        for e in entities:
            if normalize_for_match(e.name) == n or n in {normalize_for_match(a) for a in e.aliases}:
                return e
        for e in entities:
            en = normalize_for_match(e.name)
            if en and (en in n or n in en):
                return e
    return fallback


def entities_text(entities: list[Entity]) -> str:
    return "\n".join(
        f"- {e.name} ({e.role}, {e.kind})" + (f"; also known as {', '.join(e.aliases[:5])}" if e.aliases else "")
        for e in entities if e.role != "us"
    )


async def fetch_quote(ctx: RunContext, *, url: str, snippet: str, names: list[str]) -> tuple[Document | None, str | None]:
    """Open an article and pick a verifiable supporting quote: a snippet fragment, else a lead
    sentence naming the entity. Returns (stored document, quote) — quote None if nothing fits."""
    fr = await ctx.services.fetcher.fetch(url)
    if not fr.ok:
        return None, None
    ext = extract_result(fr, mode="article")
    if ext.quality != "ok" or ext.word_count < 60:
        return None, None
    async with transaction(ctx.services.session_factory) as s:
        doc = await save_document(s, workspace_id=ctx.workspace_id, url=normalize_url(url), extracted=ext, fetch=fr)
    fragments = sorted((f.strip(" .") for f in re.split(r"\.\.\.|…", snippet or "")), key=len, reverse=True)
    for frag in fragments:
        if len(frag) >= 40 and quote_in_text(frag, ext.text):
            return doc, frag
    lowered = [n.lower() for n in names if n]
    for sentence in re.split(r"(?<=[.!?])\s+", ext.text)[:40]:
        if 40 <= len(sentence) <= 400 and any(n in sentence.lower() for n in lowered):
            return doc, sentence.strip()
    return doc, None


async def process_news(
    ctx: RunContext,
    *,
    source: Source,
    results: list[SearchResult],
    entities: list[Entity],
    policy: EffectivePolicy,
    regulator_domains: list[str],
    historical: bool,
    window_days: int,
) -> NewsOutcome:
    services = ctx.services
    outcome = NewsOutcome(new_items=len(results))
    if not results:
        return outcome

    # Remember every new item, so the next check only sees what's new.
    stored: dict[str, Document] = {}
    async with transaction(services.session_factory) as s:
        for r in results:
            stored[r.url] = await save_document(
                s, workspace_id=source.workspace_id, url=normalize_url(r.url), origin="search", title=r.title,
                text=r.content or r.snippet or "", published_at=r.published_at,
                meta={"provider": r.provider, "query": source.query},
            )
    if services.llm is None:
        return outcome

    fallback = next((e for e in entities if e.id == source.entity_id), None)
    items: list[tuple[SearchResult, TriageItemOut]] = []
    for i in range(0, len(results), MAX_ITEMS_PER_BATCH):
        batch = results[i:i + MAX_ITEMS_PER_BATCH]
        triage = await triage_news(ctx, items=batch, entities_text=entities_text(entities),
                                   policy_text=policy.describe_for_prompt(), today=today_str(), window_days=window_days)
        for item in triage.items:
            if 0 <= item.id < len(batch) and item.relevant:
                items.append((batch[item.id], item))
    outcome.relevant = len(items)

    async def verify(r: SearchResult, ent: Entity | None) -> tuple[Document | None, str | None]:
        names = [ent.name, *ent.aliases] if ent else []
        return await fetch_quote(ctx, url=r.url, snippet=r.content or r.snippet or "", names=names)

    fetched = await asyncio.gather(*(verify(r, resolve_entity(it.entity, entities, fallback)) for r, it in items))

    for (r, item), (article, quote) in zip(items, fetched, strict=True):
        entity = resolve_entity(item.entity, entities, fallback)
        event_type = item.event_type if item.event_type in EVENT_TYPES else "other"
        area = item.area if item.area in policy.areas else (source.areas or ["general"])[0]
        occurred = parse_date(item.occurred_at) or r.published_at
        key = cluster_key(event_type, entity.name if entity else "unknown", counterparty=item.counterparty,
                          product=item.product, person=item.person, round_or_amount=item.round_or_amount,
                          topic=item.topic or item.headline, when=occurred)
        doc = article or stored.get(r.url)
        url = r.url
        async with transaction(services.session_factory) as s:
            existing = await find_cluster(s, workspace_id=source.workspace_id, cluster_key=key,
                                          entity_id=entity.id if entity else None, event_type=event_type,
                                          title=item.headline or r.title, around=occurred)
            material = policy.is_material(item.materiality, area, event_type)
            if existing is not None:
                event, claim_id = existing, None
                claim = await primary_claim(s, existing.id)
                claim_id = claim.id if claim else None
                outcome.merged += 1
            elif material or not historical:
                event, claim = await create_event(
                    s, workspace_id=source.workspace_id, title=item.headline or r.title, claim=item.claim or item.headline,
                    status=("historical" if historical else "candidate") if material else "filtered",
                    area=area, event_type=event_type, detection_source="news", entity_id=entity.id if entity else None,
                    source_id=source.id, summary=item.summary, detected_at=(occurred or r.published_at) if historical else None,
                    occurred_at=occurred, document_id=doc.id if doc else None, cluster_key=key,
                    materiality=item.materiality, materiality_reason=item.reason,
                    filter_tier=None if material else 2,
                    filter_reason=None if material else (
                        f"{item.reason} (materiality {item.materiality}; threshold "
                        f"{policy.threshold_for(area, event_type)})"),
                    is_historical=historical,
                    details={"counterparty": item.counterparty, "product": item.product, "person": item.person,
                             "round_or_amount": item.round_or_amount, "topic": item.topic},
                )
                claim_id = claim.id
                if material:
                    outcome.material.append(event.id)
                else:
                    outcome.filtered += 1
            else:
                continue
            if claim_id and quote and article is not None:
                domains = list(entity.official_domains) if entity else []
                await add_evidence(
                    s, workspace_id=source.workspace_id, claim_id=claim_id, url=url, quote=quote, stance="supports",
                    source_class=classify_source(url, entity_domains=domains, regulator_domains=regulator_domains,
                                                 distrusted_publishers=policy.distrusted_publishers),
                    publisher=publisher_of(url), quote_verified=True, title=article.title or r.title,
                    document_id=article.id, published_at=r.published_at,
                )
                await refresh_status(s, claim_id=claim_id, event_id=event.id, distrusted=policy.distrusted_publishers)
    return outcome
