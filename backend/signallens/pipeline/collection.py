"""Collection jobs: baseline, history backfill and scheduled checks for every source.

- **Baseline** (C18): the first successful observation of a source is recorded and its
  tracked values extracted; it can never produce an alert.
- **Backfill** (C5): monthly web-archive captures of official pages are replayed through
  the same change pipeline, producing dated history and *historical* events.
- **Check**: a scheduled look at a source. Pages: conditional GET → quality gate → hash →
  diff/values/materiality. News: search → only unseen items → triage → cluster.

Every check writes a ``SourceCheck`` row: the base of the attention funnel.
"""

from __future__ import annotations

import logging
import math
import uuid
from datetime import timedelta

from sqlalchemy import select

from signallens.db.base import utcnow
from signallens.db.models import Document, Entity, Fact, Source, SourceCheck, SourceSnapshot
from signallens.db.session import transaction
from signallens.domain.scheduling import next_interval_minutes
from signallens.fetch.extract import ExtractedDoc, extract_result
from signallens.fetch.http import FetchResult
from signallens.fetch.render import RENDERED_NOTE, render_if_js_shell
from signallens.jobs.queue import PRIORITY_BACKGROUND, PRIORITY_PIPELINE, enqueue
from signallens.pipeline.news import process_news, unseen
from signallens.pipeline.pages import (
    last_ok_snapshot,
    linked_facts,
    previous_versions,
    process_page_change,
    read_values,
)
from signallens.pipeline.quality import relative_verdict
from signallens.runtime.core import Budget, RunContext, finish_run, start_run
from signallens.runtime.services import Services
from signallens.store.documents import save_document
from signallens.store.world import effective_policy, entity_domains, record_value

log = logging.getLogger(__name__)

HISTORICAL_REPORT_CAP = 10


async def _load(services: Services, source_id: uuid.UUID):
    async with services.session_factory() as s:
        source = await s.get(Source, source_id)
        if source is None:
            raise LookupError(f"source {source_id} not found")
        entities_by_id, regulator_domains = await entity_domains(s, source.workspace_id)
        policy = await effective_policy(s, source.workspace_id)
    return source, entities_by_id, regulator_domains, policy


async def _run(services: Services, source: Source, agent: str, title: str, *, budget: Budget | None = None) -> RunContext:
    return await start_run(services, workspace_id=source.workspace_id, agent=agent, title=title,
                           task={"source_id": str(source.id), "url": source.url, "query": source.query},
                           subject_type="source", subject_id=source.id,
                           budget=budget or Budget(max_steps=0, max_tool_calls=0, max_llm_calls=40,
                                                   max_seconds=900, max_cost_usd=0.60))


async def _finish_check(services: Services, source_id: uuid.UUID, check_id: uuid.UUID, *, outcome: str,
                        http_status: int | None = None, new_items: int = 0, changes: int = 0, error: str | None = None,
                        snapshot_id: uuid.UUID | None = None, etag: str | None = None, last_modified: str | None = None,
                        baseline: bool = False) -> None:
    async with transaction(services.session_factory) as s:
        check = await s.get(SourceCheck, check_id)
        check.finished_at, check.outcome, check.http_status = utcnow(), outcome, http_status
        check.new_items, check.changes, check.error, check.snapshot_id = new_items, changes, error, snapshot_id
        src = await s.get(Source, source_id)
        failed = outcome in ("error", "blocked", "degenerate")
        src.consecutive_failures = src.consecutive_failures + 1 if failed else 0
        src.current_interval_minutes = next_interval_minutes(
            kind=src.kind, base=src.check_every_minutes, current=src.current_interval_minutes,
            outcome=outcome, failures=src.consecutive_failures,
        )
        src.last_checked_at, src.last_outcome = utcnow(), outcome
        src.next_check_at = utcnow() + timedelta(minutes=src.current_interval_minutes)
        if outcome in ("changed", "new_items"):
            src.last_changed_at = utcnow()
        if etag is not None or last_modified is not None:
            src.etag, src.last_modified = etag, last_modified
        if baseline and not failed:
            src.baselined = True


async def _render_if_needed(services: Services, source: Source, fr: FetchResult,
                            ext: ExtractedDoc) -> tuple[FetchResult, ExtractedDoc, bool]:
    """Render an empty JavaScript shell with the headless browser when enabled (never a bot challenge).

    Returns (fetch, extracted, rendered). The outcome is remembered on the source so later
    checks skip conditional requests (the raw shell's ETag says nothing about the data).
    """
    st = services.settings
    out = await render_if_js_shell(
        fr, ext, enabled=st.render_js, timeout_s=st.render_timeout_s, user_agent=st.user_agent,
        allow_private=bool(getattr(services.fetcher, "allow_private_hosts", False)), max_bytes=st.fetch_max_bytes,
        renderer=services.extras.get("renderer"),
    )
    if out.note is not None:
        ok = out.rendered and out.doc.quality == "ok"
        async with transaction(services.session_factory) as s:
            src = await s.get(Source, source.id)
            src.config = {**(src.config or {}), "js_rendered": ok, "render_note": out.note}
        source.config = {**(source.config or {}), "js_rendered": ok, "render_note": out.note}
    return out.fetch, out.doc, out.rendered and out.doc.quality == "ok"


def _render_meta(rendered: bool) -> dict:
    return {"rendered_with": "headless_browser", "render_note": RENDERED_NOTE} if rendered else {}


async def _open_check(services: Services, source: Source) -> uuid.UUID:
    check_id = uuid.uuid4()
    async with transaction(services.session_factory) as s:
        s.add(SourceCheck(id=check_id, workspace_id=source.workspace_id, source_id=source.id, started_at=utcnow()))
    return check_id


# ---------------------------------------------------------------------------------------
# Baseline
# ---------------------------------------------------------------------------------------


async def baseline_source(services: Services, source_id: uuid.UUID) -> dict:
    source, entities, regulator_domains, policy = await _load(services, source_id)
    if source.kind == "news":
        return await _news(services, source, entities, regulator_domains, policy, baseline=True)

    check_id = await _open_check(services, source)
    fr = await services.fetcher.fetch(source.url)
    if not fr.ok:
        outcome = "blocked" if fr.blocked else "error"
        await _finish_check(services, source.id, check_id, outcome=outcome, http_status=fr.status,
                            error=fr.error or fr.blocked)
        return {"outcome": outcome}
    ext = extract_result(fr, mode="page")
    fr, ext, rendered = await _render_if_needed(services, source, fr, ext)
    if ext.quality != "ok":
        await _finish_check(services, source.id, check_id, outcome="degenerate" if ext.quality == "degenerate" else "blocked",
                            http_status=fr.status, error=ext.quality_reason)
        return {"outcome": ext.quality}
    now = utcnow()
    async with transaction(services.session_factory) as s:
        doc = await save_document(s, workspace_id=source.workspace_id, url=source.url, extracted=ext, fetch=fr,
                                  origin="sandbox" if fr.from_sandbox else "live", meta=_render_meta(rendered))
        snap = SourceSnapshot(id=uuid.uuid4(), source_id=source.id, document_id=doc.id, observed_at=now,
                              is_baseline=True, origin="live", quality="ok")
        s.add(snap)
    values = 0
    if services.llm is not None:
        async with services.session_factory() as s:
            facts = await linked_facts(s, source)
        if facts:
            ctx = await _run(services, source, "extractor", f"Baseline values: {source.url}")
            try:
                if rendered:
                    await ctx.step("note", "Page rendered with a headless browser: the raw HTML is an empty "
                                           "JavaScript shell", name="render_js")
                async with services.session_factory() as s:
                    previous = await previous_versions(facts, now, s)
                readings = await read_values(ctx, facts=facts, previous=previous, doc=doc, url=source.url)
                async with transaction(services.session_factory) as s:
                    for fact, v, _prev, changed in readings:
                        if not changed:
                            continue
                        await record_value(
                            s, fact=await s.get(Fact, fact.id), display=v.value_display, number=v.number,
                            unit=v.unit, conditions=v.conditions, observed_at=now, observed_via="live",
                            evidence_status="confirmed" if source.authority in ("official", "regulator") else "single_source",
                            quote=v.quote, source_id=source.id, document_id=doc.id,
                        )
                        values += 1
                await finish_run(ctx, "succeeded", result={"values": values, "facts": len(facts)})
            except Exception as e:
                await finish_run(ctx, "failed", error=str(e))
                raise
    await _finish_check(services, source.id, check_id, outcome="baseline", http_status=fr.status, snapshot_id=snap.id,
                        etag=fr.etag, last_modified=fr.last_modified, baseline=True)
    return {"outcome": "baseline", "values": values, **({"rendered": True} if rendered else {})}


# ---------------------------------------------------------------------------------------
# Backfill from the web archive
# ---------------------------------------------------------------------------------------


async def backfill_source(services: Services, source_id: uuid.UUID) -> dict:
    source, entities, regulator_domains, policy = await _load(services, source_id)
    if source.kind != "page" or not source.url or source.url.startswith("sandbox://"):
        return {"skipped": "not an archivable page"}
    entity = entities.get(source.entity_id) if source.entity_id else None
    months = services.settings.backfill_months
    since = (utcnow() - timedelta(days=31 * months)).date()
    captures = await services.wayback.list_captures(source.url, since=since, per="month", limit=months + 2)
    ctx = await _run(services, source, "extractor", f"History backfill: {source.url}",
                     budget=Budget(max_steps=0, max_tool_calls=0, max_llm_calls=4 * len(captures) + 8,
                                   max_seconds=1800, max_cost_usd=1.00))
    await ctx.step("note", f"Found {len(captures)} monthly archive captures since {since.isoformat()}", name="wayback")
    async with services.session_factory() as s:
        live = await last_ok_snapshot(s, source.id, origin="live")
    prev_doc: Document | None = None
    prev_at = None
    last_rejected: int | None = None
    material_ids: list[uuid.UUID] = []
    used = skipped = 0
    try:
        for cap in captures:
            fr = await services.wayback.fetch_capture(cap)
            ext = extract_result(fr, mode="page") if fr.ok else None  # absolute checks
            reason = None
            if ext is None or ext.quality != "ok":
                reason = (ext.quality_reason if ext else (fr.error or f"HTTP {fr.status}")) or "unusable"
            else:
                accept, note = relative_verdict(ext.word_count, prev_doc.word_count if prev_doc else None, last_rejected)
                if not accept:
                    reason, last_rejected = note, ext.word_count
                elif note:
                    await ctx.step("note", f"Capture of {cap.captured_at.date().isoformat()} {note}", name="quality_gate")
            if reason:
                skipped += 1
                await ctx.step("guardrail", f"Skipped capture of {cap.captured_at.date().isoformat()}: {reason}",
                               name="quality_gate")
                continue
            last_rejected = None
            if prev_doc is not None and ext.content_hash == prev_doc.content_hash:
                continue
            async with transaction(services.session_factory) as s:
                doc = await save_document(s, workspace_id=source.workspace_id, url=cap.archive_url, extracted=ext, fetch=fr,
                                          origin="archive", archive_timestamp=cap.timestamp, published_at=cap.captured_at)
                s.add(SourceSnapshot(id=uuid.uuid4(), source_id=source.id, document_id=doc.id, observed_at=cap.captured_at,
                                     origin="archive", quality="ok"))
            used += 1
            if prev_doc is None:
                # Earliest usable capture: establish the oldest known values.
                if services.llm is not None:
                    async with services.session_factory() as s:
                        facts = await linked_facts(s, source)
                        previous = await previous_versions(facts, cap.captured_at, s)
                    readings = await read_values(ctx, facts=facts, previous=previous, doc=doc, url=source.url,
                                                 when_label=cap.captured_at.date().isoformat()) if facts else []
                    async with transaction(services.session_factory) as s:
                        for fact, v, _p, changed in readings:
                            if changed:
                                await record_value(s, fact=await s.get(Fact, fact.id), display=v.value_display,
                                                   number=v.number, unit=v.unit, conditions=v.conditions,
                                                   observed_at=cap.captured_at, observed_via="archive",
                                                   evidence_status="confirmed", quote=v.quote,
                                                   source_id=source.id, document_id=doc.id)
            else:
                out = await process_page_change(
                    ctx, source=source, entity=entity, policy=policy, prev_doc=prev_doc, new_doc=doc,
                    observed_at=cap.captured_at, prev_observed_at=prev_at, historical=True,
                    regulator_domains=regulator_domains,
                )
                material_ids.extend(out.material)
            prev_doc, prev_at = doc, cap.captured_at

        # Close the gap between the newest capture and today's baseline.
        if prev_doc is not None and live is not None and live[1].content_hash != prev_doc.content_hash:
            out = await process_page_change(
                ctx, source=source, entity=entity, policy=policy, prev_doc=prev_doc, new_doc=live[1],
                observed_at=live[0].observed_at, prev_observed_at=prev_at, historical=True,
                regulator_domains=regulator_domains,
            )
            material_ids.extend(out.material)

        async with transaction(services.session_factory) as s:
            src = await s.get(Source, source.id)
            src.config = {**(src.config or {}), "backfilled": True, "captures_used": used, "captures_skipped": skipped}
            for event_id in material_ids[-HISTORICAL_REPORT_CAP:]:
                await enqueue(s, "analyze_event", {"event_id": str(event_id), "historical": True},
                              workspace_id=source.workspace_id, priority=PRIORITY_BACKGROUND,
                              dedupe_key=f"analyze:{event_id}")
        await finish_run(ctx, "succeeded", result={"captures": len(captures), "used": used, "skipped": skipped,
                                                   "historical_events": len(material_ids)})
        return {"captures": len(captures), "used": used, "events": len(material_ids)}
    except Exception as e:
        await finish_run(ctx, "failed", error=f"{type(e).__name__}: {e}")
        raise


# ---------------------------------------------------------------------------------------
# Scheduled checks
# ---------------------------------------------------------------------------------------


async def check_source(services: Services, source_id: uuid.UUID) -> dict:
    source, entities, regulator_domains, policy = await _load(services, source_id)
    if not source.active:
        return {"skipped": "inactive"}
    if source.kind == "news":
        return await _news(services, source, entities, regulator_domains, policy, baseline=False)
    return await _page(services, source, entities, regulator_domains, policy)


async def _page(services: Services, source: Source, entities: dict[uuid.UUID, Entity], regulator_domains: list[str],
                policy) -> dict:
    check_id = await _open_check(services, source)
    async with services.session_factory() as s:
        last = await last_ok_snapshot(s, source.id)
    conditional = last is not None and not (source.config or {}).get("js_rendered")
    fr = await services.fetcher.fetch(source.url, etag=source.etag if conditional else None,
                                      last_modified=source.last_modified if conditional else None)
    if fr.not_modified:
        if last is not None:
            await _fill_missing_values(services, source, last[1])
        await _finish_check(services, source.id, check_id, outcome="not_modified", http_status=fr.status)
        return {"outcome": "not_modified"}
    if not fr.ok:
        outcome = "blocked" if fr.blocked else "error"
        await _finish_check(services, source.id, check_id, outcome=outcome, http_status=fr.status,
                            error=fr.error or fr.blocked)
        return {"outcome": outcome}
    ext = extract_result(fr, mode="page")  # absolute checks; relative check below
    fr, ext, rendered = await _render_if_needed(services, source, fr, ext)
    if ext.quality != "ok":
        outcome = "degenerate" if ext.quality == "degenerate" else "blocked"
        await _finish_check(services, source.id, check_id, outcome=outcome, http_status=fr.status,
                            error=ext.quality_reason)
        return {"outcome": outcome}
    accept, note = relative_verdict(ext.word_count, last[1].word_count if last else None,
                                    (source.config or {}).get("rejected_words"))
    async with transaction(services.session_factory) as s:
        src = await s.get(Source, source.id)
        src.config = {**(src.config or {}), "rejected_words": None if accept else ext.word_count}
    if not accept:
        await _finish_check(services, source.id, check_id, outcome="degenerate", http_status=fr.status, error=note)
        return {"outcome": "degenerate"}
    if last is not None and ext.content_hash == last[1].content_hash:
        await _fill_missing_values(services, source, last[1])
        await _finish_check(services, source.id, check_id, outcome="unchanged", http_status=fr.status,
                            etag=fr.etag, last_modified=fr.last_modified)
        return {"outcome": "unchanged"}

    now = utcnow()
    async with transaction(services.session_factory) as s:
        doc = await save_document(s, workspace_id=source.workspace_id, url=source.url, extracted=ext, fetch=fr,
                                  origin="sandbox" if fr.from_sandbox else "live", meta=_render_meta(rendered))
        snap = SourceSnapshot(id=uuid.uuid4(), source_id=source.id, document_id=doc.id, observed_at=now,
                              is_baseline=last is None, origin="live", quality="ok")
        s.add(snap)
    if last is None:
        # First good observation of this source is its baseline (C18).
        await _finish_check(services, source.id, check_id, outcome="baseline", http_status=fr.status,
                            snapshot_id=snap.id, etag=fr.etag, last_modified=fr.last_modified, baseline=True)
        return {"outcome": "baseline"}

    ctx = await _run(services, source, "materiality", f"Check: {source.url}")
    try:
        if rendered:
            await ctx.step("note", "Page rendered with a headless browser: the raw HTML is an empty JavaScript shell",
                           name="render_js")
        out = await process_page_change(
            ctx, source=source, entity=entities.get(source.entity_id) if source.entity_id else None, policy=policy,
            prev_doc=last[1], new_doc=doc, observed_at=now, prev_observed_at=last[0].observed_at, historical=False,
            regulator_domains=regulator_domains,
        )
        await finish_run(ctx, "succeeded", result={"changes": out.changes, "material": len(out.material),
                                                   "filtered": out.filtered})
    except Exception as e:
        await finish_run(ctx, "failed", error=f"{type(e).__name__}: {e}")
        await _finish_check(services, source.id, check_id, outcome="error", http_status=fr.status, error=str(e)[:500],
                            snapshot_id=snap.id)
        raise
    async with transaction(services.session_factory) as s:
        for event_id in out.material:
            await enqueue(s, "investigate_event", {"event_id": str(event_id)}, workspace_id=source.workspace_id,
                          priority=PRIORITY_PIPELINE, dedupe_key=f"investigate:{event_id}")
    outcome = "changed" if (out.changes and not out.noise_only) else "unchanged"
    await _finish_check(services, source.id, check_id, outcome=outcome, http_status=fr.status, changes=out.changes,
                        snapshot_id=snap.id, etag=fr.etag, last_modified=fr.last_modified)
    return {"outcome": outcome, "changes": out.changes, "material": len(out.material)}


async def _news(services: Services, source: Source, entities: dict[uuid.UUID, Entity], regulator_domains: list[str],
                policy, *, baseline: bool) -> dict:
    check_id = await _open_check(services, source)
    if services.search is None:
        await _finish_check(services, source.id, check_id, outcome="error", error="No search provider configured")
        return {"outcome": "error"}
    window = 30 if baseline else max(2, math.ceil(source.check_every_minutes * 3 / (60 * 24)))
    try:
        results = await services.search.search(source.query or "", max_results=10, recency_days=window, topic="news")
    except Exception as e:
        await _finish_check(services, source.id, check_id, outcome="error", error=f"search failed: {e}"[:500])
        return {"outcome": "error"}
    ctx = await _run(services, source, "triage", f"{'Baseline' if baseline else 'Check'} news: “{source.query}”")
    try:
        fresh = await unseen(ctx, source.workspace_id, results)
        out = await process_news(ctx, source=source, results=fresh, entities=list(entities.values()), policy=policy,
                                 regulator_domains=regulator_domains, historical=baseline, window_days=window)
        await finish_run(ctx, "succeeded", result={"results": len(results), "new": out.new_items,
                                                   "relevant": out.relevant, "merged": out.merged,
                                                   "material": len(out.material)})
    except Exception as e:
        await finish_run(ctx, "failed", error=f"{type(e).__name__}: {e}")
        await _finish_check(services, source.id, check_id, outcome="error", error=str(e)[:500])
        raise
    async with transaction(services.session_factory) as s:
        for event_id in out.material:
            if baseline:
                await enqueue(s, "analyze_event", {"event_id": str(event_id), "historical": True},
                              workspace_id=source.workspace_id, priority=PRIORITY_BACKGROUND,
                              dedupe_key=f"analyze:{event_id}")
            else:
                await enqueue(s, "investigate_event", {"event_id": str(event_id)}, workspace_id=source.workspace_id,
                              priority=PRIORITY_PIPELINE, dedupe_key=f"investigate:{event_id}")
    outcome = "baseline" if baseline else ("new_items" if out.new_items else "no_new_items")
    await _finish_check(services, source.id, check_id, outcome=outcome, new_items=out.new_items,
                        changes=len(out.material), baseline=baseline)
    return {"outcome": outcome, "new": out.new_items, "material": len(out.material)}


async def _fill_missing_values(services: Services, source: Source, doc: Document) -> int:
    """Extract tracked values that have never been read from an unchanged page.

    Covers a baseline taken before a model was configured and attributes added by a later
    plan version. Attempted once per page version (content hash), so a value that is simply
    not on the page does not cost a model call on every check.
    """
    if services.llm is None:
        return 0
    async with services.session_factory() as s:
        missing = [f for f in await linked_facts(s, source) if f.current_version_id is None]
    tried = (source.config or {}).get("missing_values_tried")
    if not missing or tried == doc.content_hash:
        return 0
    ctx = await _run(services, source, "extractor", f"Read missing values: {source.url}")
    try:
        readings = await read_values(ctx, facts=missing, previous={f.id: None for f in missing}, doc=doc,
                                     url=source.url)
        now = utcnow()
        async with transaction(services.session_factory) as s:
            for fact, v, _prev, _changed in readings:
                await record_value(
                    s, fact=await s.get(Fact, fact.id), display=v.value_display, number=v.number, unit=v.unit,
                    conditions=v.conditions, observed_at=now, observed_via="live",
                    evidence_status="confirmed" if source.authority in ("official", "regulator") else "single_source",
                    quote=v.quote, source_id=source.id, document_id=doc.id,
                )
            src = await s.get(Source, source.id)
            src.config = {**(src.config or {}), "missing_values_tried": doc.content_hash}
        await finish_run(ctx, "succeeded", result={"values": len(readings), "missing": len(missing)})
        return len(readings)
    except Exception as e:
        await finish_run(ctx, "failed", error=f"{type(e).__name__}: {e}")
        raise


async def due_sources(services: Services, *, limit: int = 50) -> list[Source]:
    async with services.session_factory() as s:
        return list((await s.execute(
            select(Source).where(Source.active.is_(True), Source.baselined.is_(True), Source.next_check_at <= utcnow())
            .order_by(Source.next_check_at).limit(limit)
        )).scalars())
