"""Investigation: run the verification agent on a material candidate event."""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import select, update

from signallens.agents.investigator import InvestigatorAgent, investigation_task
from signallens.db.base import utcnow
from signallens.db.models import Document, Entity, Event, Fact, Investigation, StateVersion
from signallens.db.session import transaction
from signallens.jobs.queue import PRIORITY_PIPELINE, enqueue
from signallens.pipeline.common import evidence_lines, parse_date, today_str
from signallens.runtime.core import Budget, RetrievedDoc, finish_run, start_run
from signallens.runtime.services import NotConfigured, Services
from signallens.store.evidence import primary_claim
from signallens.store.world import effective_policy, entity_domains, history

log = logging.getLogger(__name__)


async def investigate_event(services: Services, event_id: uuid.UUID) -> dict:
    async with transaction(services.session_factory) as s:
        event = await s.get(Event, event_id)
        if event is None or event.status != "candidate":
            return {"skipped": f"status {getattr(event, 'status', 'missing')}"}
        event.status = "investigating"
        claim = await primary_claim(s, event.id)
        entities, regulator_domains = await entity_domains(s, event.workspace_id)
        policy = await effective_policy(s, event.workspace_id)
        entity = entities.get(event.entity_id) if event.entity_id else None
        detection_doc = await s.get(Document, event.document_id) if event.document_id else None
        fact = await s.get(Fact, event.fact_id) if event.fact_id else None
        fact_hist = None
        if fact:
            versions = await history(s, fact.id)
            fact_hist = "\n".join(f"{v.observed_at.date().isoformat()}: {v.value_display} ({v.observed_via})"
                                  for v in versions[-8:])
        lines = await evidence_lines(s, claim.id) if claim else []
        counterparty = (event.details or {}).get("counterparty")
        related_domains = list(entity.official_domains) if entity else []
        if counterparty:
            for e in entities.values():
                if e.name.lower() == str(counterparty).lower():
                    related_domains += e.official_domains
        workspace_id, status_before = event.workspace_id, event.evidence_status
        snapshot = {"title": event.title, "summary": event.summary, "area": event.area, "before": event.before_display,
                    "after": event.after_display, "detection": event.detection_source, "doc": detection_doc}

    s_ = services.settings
    ctx = await start_run(
        services, workspace_id=workspace_id, agent="investigator", title=f"Investigate: {snapshot['title'][:90]}",
        task={"event_id": str(event_id), "claim": claim.statement if claim else snapshot["title"]},
        subject_type="event", subject_id=event_id,
        budget=Budget(max_steps=s_.investigation_max_steps, max_tool_calls=s_.investigation_max_steps + 4,
                      max_llm_calls=s_.investigation_max_steps + 4, max_seconds=420,
                      max_cost_usd=s_.investigation_max_cost_usd),
    )
    investigation_id = uuid.uuid4()
    async with transaction(services.session_factory) as s:
        s.add(Investigation(id=investigation_id, workspace_id=workspace_id, event_id=event_id, run_id=ctx.run_id))

    doc = snapshot["doc"]
    if doc is not None:
        ctx.remember(RetrievedDoc(url=doc.url, final_url=doc.final_url or doc.url, title=doc.title,
                                  publisher=doc.publisher, text=doc.text, published_at=doc.published_at,
                                  document_id=doc.id, is_archive=doc.origin == "archive"))
    ctx.scratch.update({
        "claim_id": claim.id, "event_id": event_id, "entity_domains": related_domains,
        "regulator_domains": regulator_domains, "distrusted": policy.distrusted_publishers,
        "entity_name": entity.name if entity else None, "evidence_status": status_before,
    })
    detection = {
        "attribute": "a tracked value changed on a monitored official page",
        "page_diff": "text changed on a monitored page",
        "news": "reported in news coverage",
    }.get(snapshot["detection"], snapshot["detection"])
    if doc is not None:
        detection += f" (detection source already opened for you: {doc.final_url or doc.url})"
    task = investigation_task(
        today=today_str(), claim=claim.statement if claim else snapshot["title"], title=snapshot["title"],
        summary=snapshot["summary"], entity_name=entity.name if entity else None,
        entity_domains=entity.official_domains if entity else [], area_label=policy.area(snapshot["area"]).label,
        before=snapshot["before"], after=snapshot["after"], detection=detection, evidence_lines=lines,
        status=status_before, fact_history=fact_hist,
    )
    try:
        result = await InvestigatorAgent(search_available=services.search is not None).run(ctx, task)
    except NotConfigured as e:
        await _fail(services, event_id, investigation_id, ctx, str(e))
        return {"error": str(e)}
    except Exception as e:
        log.exception("investigation failed")
        await _fail(services, event_id, investigation_id, ctx, f"{type(e).__name__}: {e}")
        raise

    conclusion = result.final.model_dump(mode="json") if result.final is not None else {
        "conclusion": f"Investigation stopped early ({result.detail}). Evidence gathered so far is shown.",
        "claim_holds": "unclear"}
    async with transaction(services.session_factory) as s:
        event = await s.get(Event, event_id)
        occurred = parse_date(conclusion.get("occurred_at"))
        if occurred and not event.occurred_at:
            event.occurred_at = occurred
        if occurred:
            # The fact version this change created took effect when the change happened (C9).
            await s.execute(update(StateVersion).where(StateVersion.event_id == event_id, StateVersion.valid_from.is_(None))
                            .values(valid_from=occurred))
        event.details = {**(event.details or {}), "investigation": conclusion}
        event.status = "analyzing"
        inv = await s.get(Investigation, investigation_id)
        inv.status = "completed" if result.stop_reason == "finished" else "budget_exhausted"
        inv.evidence_status, inv.conclusion, inv.finished_at = event.evidence_status, conclusion, utcnow()
        await enqueue(s, "analyze_event", {"event_id": str(event_id)}, workspace_id=workspace_id,
                      priority=PRIORITY_PIPELINE, dedupe_key=f"analyze:{event_id}")
        final_status = event.evidence_status
    await finish_run(ctx, "succeeded" if result.stop_reason == "finished" else "budget_exhausted",
                     result={"evidence_status": final_status, **conclusion})
    return {"evidence_status": final_status, "stop": result.stop_reason}


async def _fail(services: Services, event_id: uuid.UUID, investigation_id: uuid.UUID, ctx, error: str) -> None:
    async with transaction(services.session_factory) as s:
        event = await s.get(Event, event_id)
        event.status, event.filter_reason = "failed", error[:500]
        inv = await s.get(Investigation, investigation_id)
        inv.status, inv.finished_at = "failed", utcnow()
    await finish_run(ctx, "failed", error=error)


async def entity_by_name(session, workspace_id: uuid.UUID, name: str) -> Entity | None:
    return (await session.execute(select(Entity).where(Entity.workspace_id == workspace_id,
                                                       Entity.name.ilike(name)))).scalar_one_or_none()
