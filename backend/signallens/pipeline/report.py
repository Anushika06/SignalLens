"""Impact analysis → intelligence report (the card), plus world-state relationship updates."""

from __future__ import annotations

import logging
import uuid
from datetime import timedelta

from sqlalchemy import select

from signallens.agents.impact import analyze_impact
from signallens.db.models import Approval, Entity, Event, Fact, IntelligenceReport, Team, Workspace
from signallens.db.session import transaction
from signallens.domain.levels import CHANGE_LABELS
from signallens.domain.severity import clamp_severity
from signallens.jobs.queue import PRIORITY_PIPELINE, enqueue
from signallens.pipeline.activation import relate, upsert_entity
from signallens.pipeline.common import evidence_lines, today_str
from signallens.runtime.core import Budget, finish_run, start_run
from signallens.runtime.services import Services
from signallens.store.evidence import assess_claim, primary_claim
from signallens.store.world import effective_policy, history

log = logging.getLogger(__name__)

RELATION_BY_TYPE = {"partnership": "partners_with", "acquisition": "acquired", "funding": "raised_from"}


async def analyze_event(services: Services, event_id: uuid.UUID, *, historical: bool = False) -> dict:
    async with services.session_factory() as s:
        event = await s.get(Event, event_id)
        if event is None:
            return {"skipped": "missing"}
        existing = (await s.execute(select(IntelligenceReport).where(IntelligenceReport.event_id == event_id))
                    ).scalar_one_or_none()
        if existing is not None or event.status not in ("analyzing", "historical", "candidate"):
            return {"skipped": f"status {event.status}"}
        ws = await s.get(Workspace, event.workspace_id)
        teams = (await s.execute(select(Team).where(Team.workspace_id == ws.id))).scalars().all()
        policy = await effective_policy(s, ws.id)
        entity = await s.get(Entity, event.entity_id) if event.entity_id else None
        claim = await primary_claim(s, event.id)
        assessment = await assess_claim(s, claim.id, distrusted=policy.distrusted_publishers) if claim else None
        lines = await evidence_lines(s, claim.id) if claim else []
        fact = await s.get(Fact, event.fact_id) if event.fact_id else None
        hist = None
        if fact:
            hist = "\n".join(f"{v.observed_at.date().isoformat()}: {v.value_display}" for v in await history(s, fact.id))
        related_rows = (await s.execute(
            select(Event.title, Event.detected_at).where(
                Event.workspace_id == ws.id, Event.entity_id == event.entity_id, Event.id != event.id,
                Event.status.in_(("published", "historical")),
                Event.detected_at >= event.detected_at - timedelta(days=120),
            ).order_by(Event.detected_at.desc()).limit(6)
        )).all()
        related = [f"{d.date().isoformat()}: {t}" for t, d in related_rows]
        area = policy.area(event.area)
        investigation = (event.details or {}).get("investigation", {}).get("conclusion")

    is_hist = historical or event.is_historical
    ctx = await start_run(services, workspace_id=ws.id, agent="impact_analyst", title=f"Assess: {event.title[:90]}",
                          task={"event_id": str(event_id)}, subject_type="event", subject_id=event_id,
                          budget=Budget(max_steps=0, max_tool_calls=0, max_llm_calls=3, max_seconds=180,
                                        max_cost_usd=0.30))
    status = assessment.status if assessment else event.evidence_status
    summary = assessment.summary if assessment else "No evidence recorded."
    try:
        out = await analyze_impact(
            ctx, today=today_str(), profile=ws.profile, teams=[t.name for t in teams], area_label=area.label,
            area_importance=area.effective_importance, entity_name=entity.name if entity else None,
            event_type=event.event_type, title=event.title, claim=claim.statement if claim else event.title,
            before=event.before_display, after=event.after_display, evidence_status=status, evidence_summary=summary,
            evidence_lines=lines, investigation=investigation, history=hist, related=related, historical=is_hist,
            tier="fast" if is_hist else "reasoning",
        )
    except Exception as e:
        await finish_run(ctx, "failed", error=f"{type(e).__name__}: {e}")
        raise

    severity, caps = clamp_severity(out.severity, evidence_status=status, area_importance=area.effective_importance)
    by_name = {t.name.lower(): t for t in teams}
    chosen = {by_name[n.lower()].id for n in out.affected_teams if n.lower() in by_name}
    chosen |= {by_name[n.lower()].id for n in area.route_to if n.lower() in by_name}
    chosen |= {t.id for t in teams if not t.areas or event.area in t.areas}  # no areas = all areas
    evidence_summary = summary + ((" " + " ".join(assessment.notes)) if assessment and assessment.notes else "")

    async with transaction(services.session_factory) as s:
        event = await s.get(Event, event_id)
        report = IntelligenceReport(
            id=uuid.uuid4(), workspace_id=event.workspace_id, event_id=event.id, entity_id=event.entity_id,
            area=event.area, title=out.headline or event.title,
            change_label=out.change_label or CHANGE_LABELS.get(event.event_type, "Development"),
            what_changed=out.what_changed, why_it_matters=out.why_it_matters, considerations=out.considerations,
            assumptions=out.assumptions, watch_next=out.watch_next, affected_team_ids=[str(t) for t in chosen],
            severity=severity, severity_rationale=" ".join([out.severity_rationale, *caps]).strip(),
            evidence_status=status, evidence_summary=evidence_summary,
            previous_state=out.previous_state or event.before_display,
            current_state=out.current_state or event.after_display,
            detected_at=event.detected_at, occurred_at=event.occurred_at, is_historical=is_hist,
            analysis_run_id=ctx.run_id,
        )
        s.add(report)
        event.status = "historical" if is_hist else "published"
        event.severity = severity
        await _update_relationships(s, event)
        if not is_hist:
            for action in out.proposed_actions[:2]:
                s.add(Approval(
                    id=uuid.uuid4(), workspace_id=event.workspace_id, report_id=report.id,
                    action_type=action.action_type, title=action.title, reason=action.reason,
                    payload={"to": action.recipient_hint or "", "subject": out.headline, "body": action.draft},
                    requested_by="impact_analyst",
                ))
            await s.flush()
            await enqueue(s, "route_report", {"report_id": str(report.id)}, workspace_id=event.workspace_id,
                          priority=PRIORITY_PIPELINE, dedupe_key=f"route:{report.id}")
        report_id = report.id
    await finish_run(ctx, "succeeded", result={"report_id": str(report_id), "severity": severity,
                                               "evidence_status": status})
    return {"report_id": str(report_id), "severity": severity}


async def _update_relationships(s, event: Event) -> None:
    """Grow the world model: partners, acquirers, investors and executives become entities + edges."""
    details = event.details or {}
    subject = await s.get(Entity, event.entity_id) if event.entity_id else None
    if subject is None:
        return
    if event.event_type in RELATION_BY_TYPE and details.get("counterparty"):
        other = await upsert_entity(s, event.workspace_id, name=str(details["counterparty"])[:200],
                                    kind="organization", role="related")
        if other.id != subject.id:
            await relate(s, event.workspace_id, subject, RELATION_BY_TYPE[event.event_type], other, event_id=event.id)
    if event.event_type == "leadership" and details.get("person"):
        person = await upsert_entity(s, event.workspace_id, name=str(details["person"])[:200], kind="person",
                                     role="related")
        await relate(s, event.workspace_id, person, "executive_of", subject, event_id=event.id)
    if event.event_type == "product_launch" and details.get("product"):
        product = await upsert_entity(s, event.workspace_id, name=str(details["product"])[:200], kind="product",
                                      role="related")
        await relate(s, event.workspace_id, subject, "offers", product, event_id=event.id)
