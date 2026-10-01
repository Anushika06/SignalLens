"""Delivery: route reports to teams, daily digests, and executing human-approved actions.

Internal notification is autonomous (spec §16). Anything that leaves the organisation —
emailing someone outside, sharing a report externally, calling an external webhook —
only happens after a person approves it, and the result is recorded on the approval.
"""

from __future__ import annotations

import logging
import uuid

import httpx
from sqlalchemy import select, update

from signallens.db.base import utcnow
from signallens.db.models import Approval, IntelligenceReport, Notification, Team, Workspace
from signallens.db.session import transaction
from signallens.domain.levels import EVIDENCE_LABELS
from signallens.domain.severity import is_immediate
from signallens.fetch.ssrf import SSRFBlocked, assert_public_url
from signallens.notify.content import build_alert_email, build_digest_email
from signallens.notify.email import EmailSender, SendResult, build_email_sender
from signallens.runtime.services import Services
from signallens.store.world import effective_policy

log = logging.getLogger(__name__)

SLACK_PREFIX = "https://hooks.slack.com/"
SEVERITY_EMOJI = {"critical": ":red_circle:", "high": ":large_orange_circle:", "medium": ":large_yellow_circle:",
                  "low": ":large_blue_circle:"}


def report_text(r: IntelligenceReport) -> str:
    state = f"\n*Before:* {r.previous_state}\n*Now:* {r.current_state}" if r.previous_state or r.current_state else ""
    return (f"{SEVERITY_EMOJI.get(r.severity, '')} *{r.title}*  ({r.change_label} · {r.severity} · "
            f"{EVIDENCE_LABELS.get(r.evidence_status, r.evidence_status)})\n{r.what_changed}{state}\n"
            f"_Why it matters (assessment):_ {r.why_it_matters}")


async def post_slack(url: str, text: str) -> str | None:
    """Returns an error string, or None on success. Only Slack incoming-webhook URLs are allowed."""
    if not url.startswith(SLACK_PREFIX):
        return "Only https://hooks.slack.com/ webhook URLs are allowed"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(url, json={"text": text})
        return None if resp.status_code < 300 else f"Slack returned HTTP {resp.status_code}"
    except httpx.HTTPError as e:
        return f"Slack request failed: {e}"


def email_sender(services: Services) -> EmailSender | None:
    """The process's email sender (built once from settings; tests inject ``extras["email_sender"]``)."""
    if "email_sender" not in services.extras:
        services.extras["email_sender"] = build_email_sender(services.settings)
    return services.extras["email_sender"]


async def _finish_email(services: Services, note_ids: list[uuid.UUID], result: SendResult) -> None:
    async with transaction(services.session_factory) as s:
        await s.execute(update(Notification).where(Notification.id.in_(note_ids)).values(
            status="sent" if result.ok else "failed", error=None if result.ok else (result.error or "failed")[:2000],
            sent_at=utcnow() if result.ok else None,
        ))
    if not result.ok:
        log.warning("email via %s failed: %s", result.provider, result.error)


async def _claim_email(s, *, workspace_id: uuid.UUID, team_id: uuid.UUID,
                       report_ids: list[uuid.UUID]) -> dict[uuid.UUID, uuid.UUID]:
    """Insert ``pending`` email notifications for reports this team has not been emailed about yet.

    The row is written (and committed) *before* sending, so a retried job or a second worker
    sees it and never sends the same card to the same team twice.
    """
    already = set((await s.execute(select(Notification.report_id).where(
        Notification.team_id == team_id, Notification.channel == "email", Notification.report_id.in_(report_ids),
    ))).scalars())
    claimed: dict[uuid.UUID, uuid.UUID] = {}
    for rid in report_ids:
        if rid in already:
            continue
        note_id = uuid.uuid4()
        s.add(Notification(id=note_id, workspace_id=workspace_id, report_id=rid, team_id=team_id, channel="email",
                           status="pending"))
        claimed[rid] = note_id
    return claimed


async def route_report(services: Services, report_id: uuid.UUID) -> dict:
    async with services.session_factory() as s:
        report = await s.get(IntelligenceReport, report_id)
        if report is None or report.is_historical:
            return {"skipped": True}
        policy = await effective_policy(s, report.workspace_id)
        teams = (await s.execute(select(Team).where(Team.workspace_id == report.workspace_id))).scalars().all()
        ws = await s.get(Workspace, report.workspace_id)
    area = policy.area(report.area)
    immediate = is_immediate(report.severity, area.effective_importance)
    targets = [t for t in teams if str(t.id) in set(report.affected_team_ids or [])] or list(teams[:1])
    sent = queued = 0
    slack_results: list[tuple[uuid.UUID, str | None]] = []
    if immediate:
        for t in targets:
            if t.slack_webhook_url:
                slack_results.append((t.id, await post_slack(t.slack_webhook_url, report_text(report))))
    sender = email_sender(services) if immediate else None
    emails: list[tuple[Team, uuid.UUID]] = []
    async with transaction(services.session_factory) as s:
        for t in targets:
            s.add(Notification(id=uuid.uuid4(), workspace_id=report.workspace_id, report_id=report.id, team_id=t.id,
                               channel="inbox", status="sent" if immediate else "digest_queued",
                               sent_at=utcnow() if immediate else None))
            sent += immediate
            queued += not immediate
        for team_id, error in slack_results:
            s.add(Notification(id=uuid.uuid4(), workspace_id=report.workspace_id, report_id=report.id, team_id=team_id,
                               channel="slack", status="failed" if error else "sent", error=error,
                               sent_at=None if error else utcnow()))
        if sender is not None:
            for t in targets:
                if t.emails:
                    claimed = await _claim_email(s, workspace_id=report.workspace_id, team_id=t.id,
                                                 report_ids=[report.id])
                    if claimed:
                        emails.append((t, claimed[report.id]))
    emailed = 0
    for t, note_id in emails:
        content = build_alert_email(team_name=t.name, workspace_name=ws.name if ws else "",
                                    workspace_id=report.workspace_id, app_url=services.settings.public_app_url,
                                    report=report)
        result = await sender.send(to=list(t.emails), subject=content.subject, text=content.text, html=content.html)
        await _finish_email(services, [note_id], result)
        emailed += result.ok
    return {"immediate": immediate, "teams": len(targets), "slack": len(slack_results), "emails": emailed}


async def send_digest(services: Services, workspace_id: uuid.UUID) -> dict:
    """Daily digest: everything that did not warrant an immediate alert, grouped per team.

    Queued inbox items are claimed (row-locked, flipped to *sent*) in one transaction, so two
    workers never deliver the same digest. Teams with email recipients get one email listing
    their cards; each card gets an ``email`` notification row recording sent/failed.
    """
    settings = services.settings
    sender = email_sender(services) if settings.digest_email_enabled else None
    email_batches: list[tuple[Team, list[IntelligenceReport], list[uuid.UUID]]] = []
    async with transaction(services.session_factory) as s:
        rows = (await s.execute(
            select(Notification, IntelligenceReport, Team)
            .join(IntelligenceReport, IntelligenceReport.id == Notification.report_id)
            .join(Team, Team.id == Notification.team_id)
            .where(Notification.workspace_id == workspace_id, Notification.status == "digest_queued")
            .order_by(IntelligenceReport.detected_at)
            .with_for_update(of=Notification, skip_locked=True)
        )).all()
        by_team: dict[uuid.UUID, tuple[Team, list[IntelligenceReport]]] = {}
        for note, report, team in rows:
            reports = by_team.setdefault(team.id, (team, []))[1]
            if report not in reports:
                reports.append(report)
            note.status, note.channel, note.sent_at = "sent", "digest", utcnow()
        ws = await s.get(Workspace, workspace_id)
        ws.last_digest_at = utcnow()
        workspace_name = ws.name
        if sender is not None:
            for team, reports in by_team.values():
                if not team.emails:
                    continue
                claimed = await _claim_email(s, workspace_id=workspace_id, team_id=team.id,
                                             report_ids=[r.id for r in reports])
                fresh = [r for r in reports if r.id in claimed]
                if fresh:
                    email_batches.append((team, fresh, list(claimed.values())))
    for team, reports in by_team.values():
        if team.slack_webhook_url:
            lines = [f"*SignalLens daily digest — {len(reports)} update(s) for {team.name}*"]
            lines += [f"• {r.title} ({r.change_label}, {r.severity}, "
                      f"{EVIDENCE_LABELS.get(r.evidence_status, r.evidence_status)})" for r in reports[:25]]
            await post_slack(team.slack_webhook_url, "\n".join(lines))
    emailed = failed = 0
    for team, reports, note_ids in email_batches:
        content = build_digest_email(team_name=team.name, workspace_name=workspace_name, workspace_id=workspace_id,
                                     app_url=settings.public_app_url, reports=reports)
        result = await sender.send(to=list(team.emails), subject=content.subject, text=content.text,
                                   html=content.html)
        await _finish_email(services, note_ids, result)
        emailed += result.ok
        failed += not result.ok
    return {"teams": len(by_team), "items": len(rows), "emails_sent": emailed, "emails_failed": failed}


async def execute_approval(services: Services, approval_id: uuid.UUID) -> dict:
    async with services.session_factory() as s:
        approval = await s.get(Approval, approval_id)
        if approval is None or approval.status != "approved":
            return {"skipped": True}
        report = await s.get(IntelligenceReport, approval.report_id) if approval.report_id else None
    payload = approval.payload or {}
    result: dict
    try:
        if approval.action_type in ("send_external_email", "share_report_externally"):
            body = payload.get("body") or (report_text(report) if report else "")
            if payload.get("note"):
                body = f"{payload['note']}\n\n{body}"
            result = await _send_email(services, to=str(payload.get("to") or ""),
                                       subject=str(payload.get("subject") or (report.title if report else "SignalLens")),
                                       body=body)
        elif approval.action_type == "post_external_webhook":
            url = str(payload.get("url") or "")
            await assert_public_url(url)
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(url, json=payload.get("json") or {"text": report_text(report) if report else ""})
            result = {"delivered": resp.status_code < 300, "http_status": resp.status_code}
        else:
            result = {"delivered": False, "reason": f"Unknown action type {approval.action_type}"}
        status = "failed" if result.get("error") else "executed"
    except (SSRFBlocked, httpx.HTTPError, OSError) as e:
        result, status = {"delivered": False, "error": str(e)}, "failed"
    async with transaction(services.session_factory) as s:
        a = await s.get(Approval, approval_id)
        a.status, a.result, a.executed_at = status, result, utcnow()
    return result


NO_EMAIL_REASON = ("No outgoing email provider is configured (BREVO_API_KEY, RESEND_API_KEY or SL_SMTP_HOST). "
                   "The approved message is saved here so it can be sent manually.")


async def _send_email(services: Services, *, to: str, subject: str, body: str) -> dict:
    if not to or "@" not in to:
        return {"delivered": False, "reason": "No valid recipient address was given."}
    sender = email_sender(services)
    if sender is None:
        return {"delivered": False, "reason": NO_EMAIL_REASON, "to": to, "subject": subject, "body": body}
    result = await sender.send(to=[to], subject=subject, text=body)
    if not result.ok:
        return {"delivered": False, "error": result.error, "provider": result.provider, "to": to,
                "subject": subject, "body": body}
    return {"delivered": True, "to": to, "subject": subject, "provider": result.provider,
            "message_id": result.message_id}
