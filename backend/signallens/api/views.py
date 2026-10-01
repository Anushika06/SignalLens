"""Builders that turn database rows into API shapes (kept out of the route handlers)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from signallens.api import schemas as S
from signallens.api.roles import ApproverContext
from signallens.db.base import utcnow
from signallens.db.models import (
    AgentRun,
    Approval,
    Entity,
    Event,
    IntelligenceReport,
    Investigation,
    Job,
    MonitoringPolicy,
    ReportRead,
    Source,
    SourceCheck,
    StateVersion,
    UserFeedback,
    Workspace,
)
from signallens.domain.policy import EffectivePolicy


def sid(value: uuid.UUID | None) -> str | None:
    return str(value) if value else None


def area_label(policy: EffectivePolicy, key: str) -> str:
    return policy.area(key).label


async def report_summaries(
    s: AsyncSession, reports: list[IntelligenceReport], *, user_id: uuid.UUID, policy: EffectivePolicy
) -> list[S.ReportSummary]:
    if not reports:
        return []
    ids = [r.id for r in reports]
    entity_ids = {r.entity_id for r in reports if r.entity_id}
    entities = {e.id: e for e in (await s.execute(select(Entity).where(Entity.id.in_(entity_ids)))).scalars()} if entity_ids else {}
    read = set((await s.execute(select(ReportRead.report_id).where(ReportRead.user_id == user_id,
                                                                   ReportRead.report_id.in_(ids)))).scalars())
    feedback: dict[uuid.UUID, UserFeedback] = {}
    for fb in (await s.execute(select(UserFeedback).where(UserFeedback.report_id.in_(ids))
                               .order_by(UserFeedback.created_at))).scalars():
        feedback[fb.report_id] = fb
    events = {e.id: e for e in (await s.execute(select(Event).where(Event.id.in_([r.event_id for r in reports])))).scalars()}
    out = []
    for r in reports:
        ent = entities.get(r.entity_id)
        fb = feedback.get(r.id)
        ev = events.get(r.event_id)
        out.append(S.ReportSummary(
            id=str(r.id), title=r.title, change_label=r.change_label, area=r.area, area_label=area_label(policy, r.area),
            entity=S.EntityRef(id=str(ent.id), name=ent.name) if ent else None,
            event_type=ev.event_type if ev else "other", severity=r.severity, evidence_status=r.evidence_status,
            previous_state=r.previous_state, current_state=r.current_state, detected_at=r.detected_at,
            occurred_at=r.occurred_at, is_historical=r.is_historical, unread=r.id not in read,
            feedback=S.FeedbackRef(verdict=fb.verdict, reason=fb.reason) if fb else None,
        ))
    return out


async def version_outs(s: AsyncSession, versions: list[StateVersion]) -> list[S.StateVersionOut]:
    source_ids = {v.source_id for v in versions if v.source_id}
    urls = dict((await s.execute(select(Source.id, Source.url).where(Source.id.in_(source_ids)))).all()) if source_ids else {}
    return [S.StateVersionOut(
        id=str(v.id), value_display=v.value_display, valid_from=v.valid_from, observed_at=v.observed_at,
        observed_via=v.observed_via, evidence_status=v.evidence_status, source_url=urls.get(v.source_id),
        event_id=sid(v.event_id),
    ) for v in versions]


def approval_out(a: Approval, ctx: ApproverContext | None = None) -> S.Approval:
    """``ctx`` (see api/roles.py) adds the requester's name and whether the viewer may decide."""
    can, why = ctx.check(a) if ctx is not None else (False, None)
    return S.Approval(
        id=str(a.id), action_type=a.action_type, title=a.title, payload=a.payload or {}, reason=a.reason,
        requested_by=a.requested_by, report_id=sid(a.report_id), status=a.status, created_at=a.created_at,
        decided_at=a.decided_at, decided_by=a.decided_by, decision_note=a.decision_note, result=a.result,
        requested_by_user_id=sid(a.requested_by_user_id),
        requested_by_name=ctx.names.get(a.requested_by_user_id) if ctx and a.requested_by_user_id else None,
        can_decide=can, cannot_decide_reason=why,
    )


async def workspace_summary(s: AsyncSession, ws: Workspace, user_id: uuid.UUID) -> S.WorkspaceSummary:
    subjects = list((await s.execute(select(Entity.name).where(Entity.workspace_id == ws.id, Entity.role == "subject")
                                     .order_by(Entity.name))).scalars())
    unread = (await s.execute(
        select(func.count(IntelligenceReport.id)).where(
            IntelligenceReport.workspace_id == ws.id, IntelligenceReport.is_historical.is_(False),
            ~select(ReportRead.report_id).where(ReportRead.report_id == IntelligenceReport.id,
                                                ReportRead.user_id == user_id).exists(),
        )
    )).scalar_one()
    return S.WorkspaceSummary(id=str(ws.id), name=ws.name, status=ws.status, created_at=ws.created_at,
                              subjects=subjects, unread_reports=unread)


async def policy_ids(s: AsyncSession, ws_id: uuid.UUID) -> tuple[str | None, str | None]:
    rows = (await s.execute(select(MonitoringPolicy).where(MonitoringPolicy.workspace_id == ws_id)
                            .order_by(MonitoringPolicy.version.desc()))).scalars().all()
    active = next((p for p in rows if p.status == "active"), None)
    pending = next((p for p in rows if p.status in ("planning", "pending_approval")), None)
    return sid(active.id if active else None), sid(pending.id if pending else None)


async def funnel(s: AsyncSession, ws_id: uuid.UUID, *, days: int = 7) -> S.Funnel:
    since = utcnow() - timedelta(days=days)
    checks = (await s.execute(select(func.count(SourceCheck.id)).where(
        SourceCheck.workspace_id == ws_id, SourceCheck.started_at >= since,
        SourceCheck.outcome.notin_(("baseline",))))).scalar_one()
    live_events = select(Event.status, func.count(Event.id)).where(
        Event.workspace_id == ws_id, Event.is_historical.is_(False), Event.detected_at >= since,
    ).group_by(Event.status)
    counts = dict((await s.execute(live_events)).all())
    changes = sum(counts.values())
    filtered = counts.get("filtered", 0)
    investigated = (await s.execute(select(func.count(Investigation.id)).where(
        Investigation.workspace_id == ws_id, Investigation.started_at >= since))).scalar_one()
    published = (await s.execute(select(func.count(IntelligenceReport.id)).where(
        IntelligenceReport.workspace_id == ws_id, IntelligenceReport.is_historical.is_(False),
        IntelligenceReport.created_at >= since))).scalar_one()
    return S.Funnel(window_days=days, checks=checks, changes=changes, filtered=filtered,
                    material=changes - filtered, investigated=investigated, published=published)


CHECK_STATUS = {"changed": "success", "new_items": "success", "baseline": "success", "unchanged": "info",
                "not_modified": "info", "no_new_items": "info", "degenerate": "warning", "blocked": "warning",
                "error": "error"}
CHECK_WORDS = {"changed": "changes found", "new_items": "new items", "baseline": "baseline recorded",
               "unchanged": "no change", "not_modified": "not modified", "no_new_items": "nothing new",
               "degenerate": "unusable page (skipped)", "blocked": "blocked", "error": "error"}
RUN_KIND = {"planner": "plan", "investigator": "investigation", "impact_analyst": "report", "extractor": "baseline",
            "triage": "check", "materiality": "check"}


async def activity(s: AsyncSession, ws_id: uuid.UUID, *, limit: int = 20) -> list[S.ActivityItem]:
    items: list[S.ActivityItem] = []
    rows = (await s.execute(
        select(SourceCheck, Source).join(Source, Source.id == SourceCheck.source_id)
        .where(SourceCheck.workspace_id == ws_id, SourceCheck.finished_at.is_not(None))
        .order_by(SourceCheck.finished_at.desc()).limit(limit)
    )).all()
    for check, src in rows:
        target = src.url or f"news “{src.query}”"
        extra = f" ({check.new_items} new)" if check.new_items else ""
        items.append(S.ActivityItem(
            id=f"check:{check.id}", at=check.finished_at, kind="baseline" if check.outcome == "baseline" else "check",
            message=f"Checked {target}: {CHECK_WORDS.get(check.outcome, check.outcome)}{extra}",
            status=CHECK_STATUS.get(check.outcome, "info"), link=S.ActivityLink(type="source", id=str(src.id)),
        ))
    for ev in (await s.execute(select(Event).where(Event.workspace_id == ws_id, Event.is_historical.is_(False))
                               .order_by(Event.updated_at.desc()).limit(limit))).scalars():
        if ev.status == "filtered":
            items.append(S.ActivityItem(id=f"event:{ev.id}", at=ev.updated_at, kind="filtered",
                                        message=f"Ignored: {ev.title} — {ev.filter_reason or 'below threshold'}",
                                        status="info", link=S.ActivityLink(type="event", id=str(ev.id))))
        elif ev.status in ("candidate", "investigating", "analyzing"):
            verb = {"candidate": "Detected", "investigating": "Investigating", "analyzing": "Assessing impact of"}[ev.status]
            items.append(S.ActivityItem(id=f"event:{ev.id}", at=ev.updated_at,
                                        kind="change" if ev.status == "candidate" else "investigation",
                                        message=f"{verb}: {ev.title}", status="running",
                                        link=S.ActivityLink(type="event", id=str(ev.id))))
        elif ev.status == "failed":
            items.append(S.ActivityItem(id=f"event:{ev.id}", at=ev.updated_at, kind="error",
                                        message=f"Could not finish: {ev.title} — {ev.filter_reason or 'error'}",
                                        status="error", link=S.ActivityLink(type="event", id=str(ev.id))))
    for r in (await s.execute(select(IntelligenceReport).where(IntelligenceReport.workspace_id == ws_id)
                              .order_by(IntelligenceReport.created_at.desc()).limit(limit))).scalars():
        items.append(S.ActivityItem(
            id=f"report:{r.id}", at=r.created_at, kind="report",
            message=("Reconstructed history: " if r.is_historical else "New intelligence: ") + r.title,
            status="success", link=S.ActivityLink(type="report", id=str(r.id))))
    for run in (await s.execute(select(AgentRun).where(AgentRun.workspace_id == ws_id, AgentRun.agent.in_(
            ("planner", "investigator"))).order_by(AgentRun.created_at.desc()).limit(limit))).scalars():
        status = {"running": "running", "succeeded": "success", "failed": "error"}.get(run.status, "warning")
        items.append(S.ActivityItem(id=f"run:{run.id}", at=run.finished_at or run.started_at or run.created_at,
                                    kind=RUN_KIND.get(run.agent, "investigation"),
                                    message=f"{'Planner' if run.agent == 'planner' else 'Investigator'} "
                                            f"{'working on' if run.status == 'running' else run.status.replace('_', ' ') + ':'} "
                                            f"{run.title}",
                                    status=status, link=S.ActivityLink(type="run", id=str(run.id))))
    for job in (await s.execute(select(Job).where(Job.workspace_id == ws_id, Job.status == "failed")
                                .order_by(Job.finished_at.desc()).limit(5))).scalars():
        items.append(S.ActivityItem(id=f"job:{job.id}", at=job.finished_at or job.created_at, kind="error",
                                    message=f"Job {job.kind} failed: {(job.last_error or '')[:160]}", status="error",
                                    link=None))
    for a in (await s.execute(select(Approval).where(Approval.workspace_id == ws_id)
                              .order_by(Approval.created_at.desc()).limit(5))).scalars():
        items.append(S.ActivityItem(id=f"approval:{a.id}", at=a.decided_at or a.created_at, kind="approval",
                                    message=f"Approval {a.status}: {a.title}",
                                    status="warning" if a.status == "pending" else "info",
                                    link=S.ActivityLink(type="report", id=str(a.report_id)) if a.report_id else None))
    items.sort(key=lambda i: i.at or datetime.min.replace(tzinfo=UTC), reverse=True)
    return items[:limit]
