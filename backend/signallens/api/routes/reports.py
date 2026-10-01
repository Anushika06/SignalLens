"""Intelligence reports: feed, card detail, read state, feedback → learned rules, external share."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from signallens.api import schemas as S
from signallens.api.deps import Principal, current, get_workspace, session
from signallens.api.roles import approver_context, load_requester_names
from signallens.api.views import approval_out, report_summaries, sid, version_outs
from signallens.db.base import utcnow
from signallens.db.models import (
    AgentRun,
    Approval,
    Claim,
    Entity,
    Event,
    Evidence,
    Fact,
    IntelligenceReport,
    Investigation,
    LearnedRule,
    ReportRead,
    RunStep,
    Source,
    StateVersion,
    Team,
    UserFeedback,
    Workspace,
)
from signallens.domain.feedback import FeedbackContext, interpret
from signallens.domain.levels import CHANGE_LABELS
from signallens.store.world import effective_policy

router = APIRouter(prefix="/workspaces/{wid}/reports", tags=["reports"])


async def _report(s: AsyncSession, ws: Workspace, rid: uuid.UUID) -> IntelligenceReport:
    r = await s.get(IntelligenceReport, rid)
    if r is None or r.workspace_id != ws.id:
        raise HTTPException(status_code=404, detail="Report not found")
    return r


@router.get("", response_model=list[S.ReportSummary])
async def list_reports(
    severity: str | None = None, area: str | None = None, entity_id: uuid.UUID | None = None,
    evidence_status: str | None = None, historical: str = "false", limit: int = 50, before: datetime | None = None,
    ws: Workspace = Depends(get_workspace), s: AsyncSession = Depends(session), who: Principal = Depends(current),
):
    q = select(IntelligenceReport).where(IntelligenceReport.workspace_id == ws.id)
    if historical == "false":
        q = q.where(IntelligenceReport.is_historical.is_(False))
    elif historical == "true":
        q = q.where(IntelligenceReport.is_historical.is_(True))
    if severity:
        q = q.where(IntelligenceReport.severity == severity)
    if area:
        q = q.where(IntelligenceReport.area == area)
    if entity_id:
        q = q.where(IntelligenceReport.entity_id == entity_id)
    if evidence_status:
        q = q.where(IntelligenceReport.evidence_status == evidence_status)
    if before:
        q = q.where(IntelligenceReport.detected_at < before)
    rows = (await s.execute(q.order_by(IntelligenceReport.detected_at.desc()).limit(max(1, min(limit, 200))))).scalars()
    policy = await effective_policy(s, ws.id)
    return await report_summaries(s, list(rows), user_id=who.user.id, policy=policy)


@router.get("/{rid}", response_model=S.ReportDetail)
async def get_report(rid: uuid.UUID, ws: Workspace = Depends(get_workspace), s: AsyncSession = Depends(session),
                     who: Principal = Depends(current)):
    r = await _report(s, ws, rid)
    policy = await effective_policy(s, ws.id)
    summary = (await report_summaries(s, [r], user_id=who.user.id, policy=policy))[0]
    event = await s.get(Event, r.event_id)
    claim_ids = list((await s.execute(select(Claim.id).where(Claim.event_id == event.id))).scalars())
    evidence = (await s.execute(select(Evidence).where(Evidence.claim_id.in_(claim_ids))
                                .order_by(Evidence.created_at))).scalars().all() if claim_ids else []
    fact_view = None
    if event.fact_id:
        fact = await s.get(Fact, event.fact_id)
        versions = (await s.execute(select(StateVersion).where(StateVersion.fact_id == fact.id)
                                    .order_by(StateVersion.observed_at))).scalars().all()
        fact_view = S.FactWithHistory(id=str(fact.id), key=fact.key, label=fact.label,
                                      history=await version_outs(s, list(versions)))
    source = await s.get(Source, event.source_id) if event.source_id else None
    inv = (await s.execute(select(Investigation).where(Investigation.event_id == event.id)
                           .order_by(Investigation.started_at.desc()).limit(1))).scalar_one_or_none()
    inv_view = None
    if inv and inv.run_id:
        run = await s.get(AgentRun, inv.run_id)
        steps = (await s.execute(select(func.count(RunStep.id)).where(RunStep.run_id == inv.run_id))).scalar_one()
        duration = int((run.finished_at - run.started_at).total_seconds() * 1000) if run and run.finished_at and run.started_at else None
        inv_view = S.InvestigationView(run_id=str(inv.run_id), status=run.status if run else inv.status, steps=steps,
                                       tool_calls=(run.usage or {}).get("tool_calls", 0) if run else 0,
                                       duration_ms=duration, conclusion=(inv.conclusion or {}).get("conclusion"))
    teams = (await s.execute(select(Team).where(Team.workspace_id == ws.id))).scalars().all()
    wanted = set(r.affected_team_ids or [])
    approvals = list((await s.execute(select(Approval).where(Approval.report_id == r.id)
                                      .order_by(Approval.created_at))).scalars())
    approver = await approver_context(s, ws, who.user.id)
    await load_requester_names(s, approver, approvals)
    related_rows = (await s.execute(select(IntelligenceReport).where(
        IntelligenceReport.workspace_id == ws.id, IntelligenceReport.id != r.id,
        IntelligenceReport.entity_id == r.entity_id, IntelligenceReport.area == r.area,
    ).order_by(IntelligenceReport.detected_at.desc()).limit(5))).scalars().all()
    return S.ReportDetail(
        **summary.model_dump(),
        what_changed=r.what_changed, why_it_matters=r.why_it_matters, considerations=r.considerations or [],
        assumptions=r.assumptions or [], watch_next=r.watch_next or [],
        affected_teams=[S.EntityRef(id=str(t.id), name=t.name) for t in teams if str(t.id) in wanted],
        evidence_summary=r.evidence_summary,
        evidence=[S.EvidenceOut(id=str(e.id), url=e.url, title=e.title, publisher=e.publisher,
                                source_class=e.source_class, is_archive=e.is_archive, stance=e.stance, quote=e.quote,
                                quote_verified=e.quote_verified, published_at=e.published_at,
                                retrieved_at=e.retrieved_at, added_by=e.added_by) for e in evidence],
        fact=fact_view,
        event=S.EventView(id=str(event.id), status=event.status, detection_source=event.detection_source,
                          materiality=event.materiality, materiality_reason=event.materiality_reason,
                          source_url=source.url if source and source.kind == "page" else None,
                          diff_excerpt=event.diff_excerpt),
        investigation=inv_view, analysis_run_id=sid(r.analysis_run_id),
        approvals=[approval_out(a, approver) for a in approvals],
        related=await report_summaries(s, list(related_rows), user_id=who.user.id, policy=policy),
    )


@router.post("/{rid}/read", status_code=204)
async def mark_read(rid: uuid.UUID, ws: Workspace = Depends(get_workspace), s: AsyncSession = Depends(session),
                    who: Principal = Depends(current)):
    r = await _report(s, ws, rid)
    await s.execute(insert(ReportRead).values(report_id=r.id, user_id=who.user.id, read_at=utcnow())
                    .on_conflict_do_nothing())
    return Response(status_code=204)


def _rule_out(rule: LearnedRule) -> S.LearnedRuleOut:
    return S.LearnedRuleOut(id=str(rule.id), kind=rule.kind, explanation=rule.explanation,
                            scope={k: str(v) for k, v in (rule.scope or {}).items()},
                            effect={k: str(v) for k, v in (rule.effect or {}).items()},
                            evidence_count=rule.evidence_count, active=rule.active, created_at=rule.created_at,
                            revoked_at=rule.revoked_at)


@router.post("/{rid}/feedback", response_model=S.FeedbackResult)
async def feedback(rid: uuid.UUID, body: S.FeedbackIn, ws: Workspace = Depends(get_workspace),
                   s: AsyncSession = Depends(session), who: Principal = Depends(current)):
    r = await _report(s, ws, rid)
    event = await s.get(Event, r.event_id)
    policy = await effective_policy(s, ws.id)
    area = policy.area(r.area)
    fb = UserFeedback(id=uuid.uuid4(), workspace_id=ws.id, report_id=r.id, user_id=who.user.id, verdict=body.verdict,
                      reason=body.reason, note=body.note)
    s.add(fb)
    await s.flush()
    prior = (await s.execute(
        select(func.count(UserFeedback.id)).join(IntelligenceReport, IntelligenceReport.id == UserFeedback.report_id)
        .join(Event, Event.id == IntelligenceReport.event_id)
        .where(UserFeedback.workspace_id == ws.id, UserFeedback.reason == body.reason, UserFeedback.id != fb.id,
               IntelligenceReport.area == r.area, Event.event_type == event.event_type,
               UserFeedback.created_at >= utcnow() - timedelta(days=60))
    )).scalar_one()
    claim_ids = list((await s.execute(select(Claim.id).where(Claim.event_id == event.id))).scalars())
    ev_rows = (await s.execute(select(Evidence).where(Evidence.claim_id.in_(claim_ids), Evidence.stance == "supports",
                                                      Evidence.quote_verified.is_(True)))).scalars().all() if claim_ids else []
    entity = await s.get(Entity, r.entity_id) if r.entity_id else None
    outcome = interpret(FeedbackContext(
        verdict=body.verdict, reason=body.reason, area=r.area, area_label=area.label, event_type=event.event_type,
        event_type_label=CHANGE_LABELS.get(event.event_type, "Development"), entity_name=entity.name if entity else None,
        report_title=r.title, effective_importance=area.effective_importance,
        current_threshold=policy.threshold_for(r.area, event.event_type),
        independent_publishers=sorted({e.publisher for e in ev_rows if e.source_class == "independent"}),
        primary_publishers=sorted({e.publisher for e in ev_rows if e.source_class == "primary"}),
        prior_same_signal=prior,
    ))
    created: list[LearnedRule] = []
    for p in outcome.proposals:
        existing = (await s.execute(select(LearnedRule).where(
            LearnedRule.workspace_id == ws.id, LearnedRule.kind == p.kind, LearnedRule.active.is_(True),
        ))).scalars().all()
        match = next((x for x in existing if x.scope == p.scope), None)
        if match is not None:
            match.effect, match.explanation = p.effect, p.explanation
            match.evidence_count += 1
            match.feedback_ids = [*match.feedback_ids, str(fb.id)]
            created.append(match)
        else:
            rule = LearnedRule(id=uuid.uuid4(), workspace_id=ws.id, kind=p.kind, scope=p.scope, effect=p.effect,
                               explanation=p.explanation, evidence_count=prior + 1, feedback_ids=[str(fb.id)])
            s.add(rule)
            created.append(rule)
    await s.flush()
    return S.FeedbackResult(
        feedback=S.FeedbackOut(id=str(fb.id), verdict=fb.verdict, reason=fb.reason, note=fb.note, created_at=fb.created_at),
        learned_rules=[_rule_out(x) for x in created], message=outcome.message,
    )


@router.post("/{rid}/share", response_model=S.Approval)
async def share(rid: uuid.UUID, body: S.ShareIn, ws: Workspace = Depends(get_workspace),
                s: AsyncSession = Depends(session), who: Principal = Depends(current)):
    r = await _report(s, ws, rid)
    a = Approval(id=uuid.uuid4(), workspace_id=ws.id, report_id=r.id, action_type="share_report_externally",
                 title=f"Share “{r.title}” with {body.to}",
                 payload={"to": body.to, "note": body.note or "", "subject": f"SignalLens: {r.title}"},
                 reason=f"Requested by {who.user.name}", requested_by="user", requested_by_user_id=who.user.id)
    s.add(a)
    await s.flush()
    approver = await approver_context(s, ws, who.user.id)
    await load_requester_names(s, approver, [a])
    return approval_out(a, approver)
