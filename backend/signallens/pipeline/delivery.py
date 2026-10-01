"""Delivery: route reports to teams, daily digests, and executing human-approved actions.

Internal notification is autonomous (spec §16). Anything that leaves the organisation —
emailing someone outside, sharing a report externally, calling an external webhook —
only happens after a person approves it, and the result is recorded on the approval.
"""

from __future__ import annotations

import asyncio
import logging
import smtplib
import uuid
from email.message import EmailMessage

import httpx
from sqlalchemy import select

from signallens.db.base import utcnow
from signallens.db.models import Approval, IntelligenceReport, Notification, Team, Workspace
from signallens.db.session import transaction
from signallens.domain.levels import EVIDENCE_LABELS
from signallens.domain.severity import is_immediate
from signallens.fetch.ssrf import SSRFBlocked, assert_public_url
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


async def route_report(services: Services, report_id: uuid.UUID) -> dict:
    async with services.session_factory() as s:
        report = await s.get(IntelligenceReport, report_id)
        if report is None or report.is_historical:
            return {"skipped": True}
        policy = await effective_policy(s, report.workspace_id)
        teams = (await s.execute(select(Team).where(Team.workspace_id == report.workspace_id))).scalars().all()
    area = policy.area(report.area)
    immediate = is_immediate(report.severity, area.effective_importance)
    targets = [t for t in teams if str(t.id) in set(report.affected_team_ids or [])] or list(teams[:1])
    sent = queued = 0
    slack_results: list[tuple[uuid.UUID, str | None]] = []
    if immediate:
        for t in targets:
            if t.slack_webhook_url:
                slack_results.append((t.id, await post_slack(t.slack_webhook_url, report_text(report))))
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
    return {"immediate": immediate, "teams": len(targets), "slack": len(slack_results)}


async def send_digest(services: Services, workspace_id: uuid.UUID) -> dict:
    """Daily digest: everything that did not warrant an immediate alert, grouped per team."""
    async with transaction(services.session_factory) as s:
        rows = (await s.execute(
            select(Notification, IntelligenceReport, Team)
            .join(IntelligenceReport, IntelligenceReport.id == Notification.report_id)
            .join(Team, Team.id == Notification.team_id)
            .where(Notification.workspace_id == workspace_id, Notification.status == "digest_queued")
        )).all()
        by_team: dict[uuid.UUID, tuple[Team, list[IntelligenceReport]]] = {}
        for note, report, team in rows:
            by_team.setdefault(team.id, (team, []))[1].append(report)
            note.status, note.channel, note.sent_at = "sent", "digest", utcnow()
        ws = await s.get(Workspace, workspace_id)
        ws.last_digest_at = utcnow()
    for team, reports in by_team.values():
        if team.slack_webhook_url:
            lines = [f"*SignalLens daily digest — {len(reports)} update(s) for {team.name}*"]
            lines += [f"• {r.title} ({r.change_label}, {r.severity}, "
                      f"{EVIDENCE_LABELS.get(r.evidence_status, r.evidence_status)})" for r in reports[:25]]
            await post_slack(team.slack_webhook_url, "\n".join(lines))
    return {"teams": len(by_team), "items": len(rows)}


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
        status = "executed"
    except (SSRFBlocked, httpx.HTTPError, OSError) as e:
        result, status = {"delivered": False, "error": str(e)}, "failed"
    async with transaction(services.session_factory) as s:
        a = await s.get(Approval, approval_id)
        a.status, a.result, a.executed_at = status, result, utcnow()
    return result


async def _send_email(services: Services, *, to: str, subject: str, body: str) -> dict:
    st = services.settings
    if not to or "@" not in to:
        return {"delivered": False, "reason": "No valid recipient address was given."}
    if not (st.smtp_host and st.smtp_from):
        return {"delivered": False,
                "reason": "No outgoing mail server is configured (SL_SMTP_*). The approved message is saved here "
                          "so it can be sent manually.",
                "to": to, "subject": subject, "body": body}

    def send() -> None:
        msg = EmailMessage()
        msg["From"], msg["To"], msg["Subject"] = st.smtp_from, to, subject
        msg.set_content(body)
        with smtplib.SMTP(st.smtp_host, st.smtp_port, timeout=20) as smtp:
            smtp.starttls()
            if st.smtp_user:
                smtp.login(st.smtp_user, st.smtp_password or "")
            smtp.send_message(msg)

    await asyncio.to_thread(send)
    return {"delivered": True, "to": to, "subject": subject}
