"""Workspaces, company profile, teams, dashboard overview, activity and inbox."""

from __future__ import annotations

import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from signallens.api import schemas as S
from signallens.api.deps import Principal, current, get_workspace, services, session
from signallens.api.roles import OWNER, ensure_member, is_approver
from signallens.api.views import activity, funnel, policy_ids, report_summaries, workspace_summary
from signallens.db.base import utcnow
from signallens.db.models import (
    Approval,
    Entity,
    Fact,
    IntelligenceReport,
    Notification,
    Source,
    Team,
    Workspace,
    WorkspaceMember,
)
from signallens.notify.content import build_test_email
from signallens.notify.email import email_status
from signallens.pipeline.delivery import email_sender
from signallens.runtime.services import Services
from signallens.store.world import effective_policy

router = APIRouter(prefix="/workspaces", tags=["workspaces"])

DEFAULT_TEAMS = [
    ("Strategy", []),  # empty = all areas
    ("Product", ["products", "pricing", "technology"]),
    ("Compliance", ["regulation", "legal"]),
    ("Sales & BD", ["partnerships", "pricing", "customers"]),
    ("Leadership", ["funding", "leadership", "acquisitions"]),
]


def team_out(t: Team) -> S.Team:
    return S.Team(id=str(t.id), name=t.name, areas=list(t.areas or []), members=list(t.members or []),
                  slack_configured=bool(t.slack_webhook_url), emails=list(t.emails or []))


async def _member(s: AsyncSession, ws: Workspace, who: Principal) -> WorkspaceMember:
    return await ensure_member(s, ws, who.user.id)


async def _detail(s: AsyncSession, ws: Workspace, who: Principal) -> S.WorkspaceDetail:
    summary = await workspace_summary(s, ws, who.user.id)
    teams = (await s.execute(select(Team).where(Team.workspace_id == ws.id).order_by(Team.created_at))).scalars().all()
    active_id, pending_id = await policy_ids(s, ws.id)
    member = await _member(s, ws, who)
    return S.WorkspaceDetail(**summary.model_dump(), profile=S.CompanyProfile(**(ws.profile or {})),
                             teams=[team_out(t) for t in teams], active_policy_id=active_id,
                             pending_policy_id=pending_id, last_seen_at=member.last_seen_at,
                             my_role=member.role, can_approve=is_approver(member.role),
                             can_manage_members=is_approver(member.role))


@router.get("", response_model=list[S.WorkspaceSummary])
async def list_workspaces(s: AsyncSession = Depends(session), who: Principal = Depends(current)):
    rows = (await s.execute(select(Workspace).where(Workspace.org_id == who.org.id)
                            .order_by(Workspace.created_at.desc()))).scalars().all()
    return [await workspace_summary(s, ws, who.user.id) for ws in rows]


@router.post("", response_model=S.WorkspaceDetail)
async def create_workspace(body: S.WorkspaceCreate, s: AsyncSession = Depends(session),
                           who: Principal = Depends(current)):
    ws = Workspace(id=uuid.uuid4(), org_id=who.org.id, name=body.name.strip(), status="setup",
                   profile=(body.profile or S.CompanyProfile()).model_dump())
    s.add(ws)
    await s.flush()
    teams = body.teams if body.teams is not None else [S.TeamInput(name=n, areas=a) for n, a in DEFAULT_TEAMS]
    for t in teams:
        s.add(Team(id=uuid.uuid4(), workspace_id=ws.id, name=t.name, areas=t.areas, members=t.members,
                   slack_webhook_url=t.slack_webhook_url or None, emails=t.emails))
    s.add(WorkspaceMember(workspace_id=ws.id, user_id=who.user.id, role=OWNER))
    await s.flush()
    return await _detail(s, ws, who)


@router.get("/{wid}", response_model=S.WorkspaceDetail)
async def get_ws(ws: Workspace = Depends(get_workspace), s: AsyncSession = Depends(session),
                 who: Principal = Depends(current)):
    return await _detail(s, ws, who)


@router.patch("/{wid}", response_model=S.WorkspaceDetail)
async def patch_ws(body: S.WorkspacePatch, ws: Workspace = Depends(get_workspace), s: AsyncSession = Depends(session),
                   who: Principal = Depends(current)):
    ws = await s.merge(ws)
    if body.name is not None:
        ws.name = body.name.strip() or ws.name
    if body.profile is not None:
        ws.profile = body.profile.model_dump()
    await s.flush()
    return await _detail(s, ws, who)


@router.post("/{wid}/seen", response_model=S.SeenOut)
async def mark_seen(ws: Workspace = Depends(get_workspace), s: AsyncSession = Depends(session),
                    who: Principal = Depends(current)):
    member = await _member(s, ws, who)
    previous, now = member.last_seen_at, utcnow()
    member.last_seen_at = now
    return S.SeenOut(previous_seen_at=previous, seen_at=now)


# --- teams ----------------------------------------------------------------------------------
@router.get("/{wid}/teams", response_model=list[S.Team])
async def list_teams(ws: Workspace = Depends(get_workspace), s: AsyncSession = Depends(session)):
    rows = (await s.execute(select(Team).where(Team.workspace_id == ws.id).order_by(Team.created_at))).scalars()
    return [team_out(t) for t in rows]


def _check_webhook(url: str | None) -> None:
    if url and not url.startswith("https://hooks.slack.com/"):
        raise HTTPException(status_code=422, detail="Slack webhook URLs must start with https://hooks.slack.com/")


@router.post("/{wid}/teams", response_model=S.Team)
async def create_team(body: S.TeamInput, ws: Workspace = Depends(get_workspace), s: AsyncSession = Depends(session)):
    _check_webhook(body.slack_webhook_url)
    t = Team(id=uuid.uuid4(), workspace_id=ws.id, name=body.name, areas=body.areas, members=body.members,
             slack_webhook_url=body.slack_webhook_url or None, emails=body.emails)
    s.add(t)
    await s.flush()
    return team_out(t)


async def _team(s: AsyncSession, ws: Workspace, tid: uuid.UUID) -> Team:
    t = await s.get(Team, tid)
    if t is None or t.workspace_id != ws.id:
        raise HTTPException(status_code=404, detail="Team not found")
    return t


@router.patch("/{wid}/teams/{tid}", response_model=S.Team)
async def patch_team(tid: uuid.UUID, body: S.TeamPatch, ws: Workspace = Depends(get_workspace),
                     s: AsyncSession = Depends(session)):
    t = await _team(s, ws, tid)
    data = body.model_dump(exclude_unset=True)
    if "slack_webhook_url" in data:
        _check_webhook(data["slack_webhook_url"])
        t.slack_webhook_url = data.pop("slack_webhook_url") or None
    for k, v in data.items():
        if v is not None:
            setattr(t, k, v)
    return team_out(t)


@router.delete("/{wid}/teams/{tid}", status_code=204)
async def delete_team(tid: uuid.UUID, ws: Workspace = Depends(get_workspace), s: AsyncSession = Depends(session)):
    await s.delete(await _team(s, ws, tid))
    return Response(status_code=204)


@router.post("/{wid}/teams/{tid}/test-email", response_model=S.EmailTestResult)
async def test_team_email(tid: uuid.UUID, ws: Workspace = Depends(get_workspace), s: AsyncSession = Depends(session),
                          svc: Services = Depends(services)):
    """Send a test email to the team's saved recipients through the configured provider."""
    t = await _team(s, ws, tid)
    recipients = list(t.emails or [])
    if not recipients:
        raise HTTPException(status_code=422, detail="Add at least one recipient email to this team and save first.")
    status = email_status(svc.settings)
    sender = email_sender(svc)
    if sender is None:
        return S.EmailTestResult(delivered=False, provider=status.provider, recipients=recipients,
                                 error=status.reason or "Email is not configured on this deployment.")
    content = build_test_email(team_name=t.name, workspace_name=ws.name, provider_label=status.label,
                               app_url=svc.settings.public_app_url, workspace_id=ws.id)
    result = await sender.send(to=recipients, subject=content.subject, text=content.text, html=content.html)
    return S.EmailTestResult(delivered=result.ok, provider=result.provider, recipients=recipients,
                             message_id=result.message_id, error=result.error)


# --- overview / activity / inbox ---------------------------------------------------------------
@router.get("/{wid}/overview", response_model=S.Overview)
async def overview(ws: Workspace = Depends(get_workspace), s: AsyncSession = Depends(session),
                   who: Principal = Depends(current)):
    policy = await effective_policy(s, ws.id)
    member = await _member(s, ws, who)
    since_30 = utcnow() - timedelta(days=30)
    subjects = []
    for e in (await s.execute(select(Entity).where(Entity.workspace_id == ws.id, Entity.role == "subject")
                              .order_by(Entity.name))).scalars():
        facts_count = (await s.execute(select(func.count(Fact.id)).where(Fact.entity_id == e.id, Fact.active.is_(True)))).scalar_one()
        reports_30d = (await s.execute(select(func.count(IntelligenceReport.id)).where(
            IntelligenceReport.entity_id == e.id, IntelligenceReport.is_historical.is_(False),
            IntelligenceReport.detected_at >= since_30))).scalar_one()
        last = (await s.execute(select(func.max(IntelligenceReport.detected_at)).where(
            IntelligenceReport.entity_id == e.id))).scalar_one_or_none()
        areas = sorted({a for src in (await s.execute(select(Source.areas).where(Source.entity_id == e.id,
                                                                                    Source.active.is_(True)))).scalars()
                        for a in (src or [])})
        subjects.append(S.SubjectCard(entity_id=str(e.id), name=e.name, kind=e.kind, role=e.role, areas=areas,
                                      facts_count=facts_count, reports_30d=reports_30d, last_change_at=last))
    recent = (await s.execute(select(IntelligenceReport).where(
        IntelligenceReport.workspace_id == ws.id, IntelligenceReport.is_historical.is_(False))
        .order_by(IntelligenceReport.detected_at.desc()).limit(12))).scalars().all()
    historical = (await s.execute(select(func.count(IntelligenceReport.id)).where(
        IntelligenceReport.workspace_id == ws.id, IntelligenceReport.is_historical.is_(True)))).scalar_one()
    pending = (await s.execute(select(func.count(Approval.id)).where(Approval.workspace_id == ws.id,
                                                                     Approval.status == "pending"))).scalar_one()
    srcs = (await s.execute(select(Source).where(Source.workspace_id == ws.id))).scalars().all()
    active = [x for x in srcs if x.active]
    next_at = min((x.next_check_at for x in active if x.next_check_at), default=None)
    return S.Overview(
        workspace=await workspace_summary(s, ws, who.user.id),
        last_seen_at=member.last_seen_at,
        subjects=subjects,
        areas=[S.AreaView(key=a.key, label=a.label, importance=a.importance,
                          effective_importance=a.effective_importance) for a in policy.areas.values()],
        funnel=await funnel(s, ws.id),
        recent_reports=await report_summaries(s, list(recent), user_id=who.user.id, policy=policy),
        historical_count=historical,
        activity=await activity(s, ws.id, limit=20),
        pending_approvals=pending,
        sources=S.SourcesHealth(total=len(srcs), active=len(active),
                                failing=sum(1 for x in active if x.consecutive_failures >= 2), next_check_at=next_at),
    )


@router.get("/{wid}/activity", response_model=list[S.ActivityItem])
async def get_activity(limit: int = 50, ws: Workspace = Depends(get_workspace), s: AsyncSession = Depends(session)):
    return await activity(s, ws.id, limit=max(1, min(limit, 200)))


@router.get("/{wid}/notifications", response_model=list[S.NotificationItem])
async def notifications(unread: bool = False, limit: int = 50, ws: Workspace = Depends(get_workspace),
                        s: AsyncSession = Depends(session)):
    q = (select(Notification, IntelligenceReport, Team)
         .join(IntelligenceReport, IntelligenceReport.id == Notification.report_id)
         .outerjoin(Team, Team.id == Notification.team_id)
         .where(Notification.workspace_id == ws.id, Notification.channel.in_(("inbox", "digest"))))
    if unread:
        q = q.where(Notification.read_at.is_(None))
    rows = (await s.execute(q.order_by(Notification.created_at.desc()).limit(max(1, min(limit, 200))))).all()
    return [S.NotificationItem(id=str(n.id), report_id=str(r.id), title=r.title, severity=r.severity,
                               team=t.name if t else None, channel=n.channel, status=n.status,
                               created_at=n.created_at, read_at=n.read_at) for n, r, t in rows]


@router.post("/{wid}/notifications/read-all", status_code=204)
async def read_all(ws: Workspace = Depends(get_workspace), s: AsyncSession = Depends(session)):
    await s.execute(update(Notification).where(Notification.workspace_id == ws.id, Notification.read_at.is_(None))
                    .values(read_at=utcnow()))
    return Response(status_code=204)
