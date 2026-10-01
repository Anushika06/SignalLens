"""Email bodies (HTML + plain text) for the daily digest, immediate alerts and test emails.

Pure functions over report-like objects so they are easy to test and preview. Every value
that comes from a page or a model is HTML-escaped; links point at the web app
(``settings.public_app_url``), never at anything a page supplied.
"""

from __future__ import annotations

import html
from dataclasses import dataclass
from typing import Protocol

from signallens.domain.levels import EVIDENCE_LABELS

SEVERITY_ORDER = ("critical", "high", "medium", "low")
SEVERITY_COLORS = {"critical": "#b91c1c", "high": "#c2410c", "medium": "#a16207", "low": "#1d4ed8"}
EVIDENCE_COLORS = {"confirmed": "#15803d", "corroborated": "#15803d", "single_source": "#a16207",
                   "conflicting": "#b91c1c", "unverified": "#6b7280"}
WHY_MAX_CHARS = 240
MAX_DIGEST_ITEMS = 50


class ReportLike(Protocol):
    id: object
    title: str
    severity: str
    evidence_status: str
    change_label: str
    why_it_matters: str
    what_changed: str


@dataclass
class EmailContent:
    subject: str
    text: str
    html: str


def report_url(app_url: str, workspace_id: object, report_id: object) -> str:
    """The card's page in the web app (frontend route ``/w/{wid}/intel/{rid}``)."""
    return f"{app_url.rstrip('/')}/w/{workspace_id}/intel/{report_id}"


def short(text: str | None, limit: int = WHY_MAX_CHARS) -> str:
    """One or two lines: collapse whitespace and cut at a word boundary."""
    s = " ".join((text or "").split())
    if len(s) <= limit:
        return s
    cut = s[:limit].rsplit(" ", 1)[0].rstrip(",;:-–—")
    return f"{cut}…"


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def summary_line(reports: list[ReportLike]) -> str:
    """e.g. "3 new changes, 1 high, 2 medium"."""
    counts = {sev: sum(1 for r in reports if r.severity == sev) for sev in SEVERITY_ORDER}
    parts = [f"{counts[sev]} {sev}" for sev in SEVERITY_ORDER if counts[sev]]
    return ", ".join([f"{_plural(len(reports), 'new change')}", *parts])


def _sorted(reports: list[ReportLike]) -> list[ReportLike]:
    rank = {s: i for i, s in enumerate(SEVERITY_ORDER)}
    return sorted(reports, key=lambda r: rank.get(r.severity, len(rank)))


def _evidence(r: ReportLike) -> str:
    return EVIDENCE_LABELS.get(r.evidence_status, r.evidence_status.replace("_", " ").capitalize())


def _badge(text: str, color: str) -> str:
    return (f'<span style="display:inline-block;padding:1px 8px;border-radius:999px;border:1px solid {color};'
            f'color:{color};font-size:12px;line-height:18px;">{html.escape(text)}</span>')


def _card_html(r: ReportLike, url: str) -> str:
    sev = r.severity
    return (
        '<tr><td style="padding:14px 0;border-top:1px solid #e5e7eb;">'
        f'<a href="{html.escape(url, quote=True)}" style="color:#111827;font-size:15px;font-weight:600;'
        f'text-decoration:none;">{html.escape(r.title)}</a>'
        '<div style="margin:6px 0;">'
        f'{_badge(sev.capitalize(), SEVERITY_COLORS.get(sev, "#6b7280"))} '
        f'{_badge(_evidence(r), EVIDENCE_COLORS.get(r.evidence_status, "#6b7280"))} '
        f'<span style="color:#6b7280;font-size:12px;">{html.escape(r.change_label or "")}</span></div>'
        f'<div style="color:#374151;font-size:14px;line-height:20px;">'
        f'<span style="color:#6b7280;">Why it matters:</span> {html.escape(short(r.why_it_matters))}</div>'
        f'<div style="margin-top:6px;"><a href="{html.escape(url, quote=True)}" style="color:#4f46e5;font-size:13px;">'
        'Open the card &rarr;</a></div>'
        '</td></tr>'
    )


def _layout(*, heading: str, intro: str, body_rows: str, footer: str) -> str:
    return (
        '<!doctype html><html><body style="margin:0;padding:0;background:#f3f4f6;">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f3f4f6;">'
        '<tr><td align="center" style="padding:24px 12px;">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        'style="max-width:620px;background:#ffffff;border-radius:12px;padding:24px;'
        'font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;">'
        '<tr><td style="color:#4f46e5;font-size:13px;font-weight:600;letter-spacing:.02em;">SignalLens</td></tr>'
        f'<tr><td style="padding-top:6px;color:#111827;font-size:20px;font-weight:700;">{html.escape(heading)}</td></tr>'
        f'<tr><td style="padding:6px 0 10px;color:#4b5563;font-size:14px;">{html.escape(intro)}</td></tr>'
        f'{body_rows}'
        f'<tr><td style="padding-top:18px;border-top:1px solid #e5e7eb;color:#9ca3af;font-size:12px;">'
        f'{footer}</td></tr>'
        '</table></td></tr></table></body></html>'
    )


def _footer_html(team_name: str, settings_url: str) -> str:
    return (f"You receive this because you are a recipient for the {html.escape(team_name)} team. "
            f'Change recipients in <a href="{html.escape(settings_url, quote=True)}" style="color:#6b7280;">'
            "workspace settings</a>.")


def build_digest_email(*, team_name: str, workspace_name: str, workspace_id: object, app_url: str,
                       reports: list[ReportLike]) -> EmailContent:
    """One email per team: undelivered digest cards grouped by severity."""
    ordered = _sorted(reports)[:MAX_DIGEST_ITEMS]
    summary = summary_line(reports)
    has_urgent = any(r.severity in ("critical", "high") for r in reports)
    subject = f"SignalLens digest for {team_name}: {summary}"
    settings_url = f"{app_url.rstrip('/')}/w/{workspace_id}/settings"
    intro = f"{workspace_name} · {summary}"

    text_lines = [f"SignalLens daily digest — {team_name}", intro, ""]
    rows: list[str] = []
    for sev in SEVERITY_ORDER:
        group = [r for r in ordered if r.severity == sev]
        if not group:
            continue
        text_lines.append(f"== {sev.upper()} ({len(group)}) ==")
        rows.append(f'<tr><td style="padding:16px 0 2px;color:{SEVERITY_COLORS[sev]};font-size:12px;'
                    f'font-weight:700;text-transform:uppercase;letter-spacing:.06em;">{sev} · {len(group)}</td></tr>')
        for r in group:
            url = report_url(app_url, workspace_id, r.id)
            text_lines += [f"- {r.title}",
                           f"  {sev.capitalize()} · {_evidence(r)}" + (f" · {r.change_label}" if r.change_label else ""),
                           f"  Why it matters: {short(r.why_it_matters)}",
                           f"  {url}", ""]
            rows.append(_card_html(r, url))
    if len(reports) > len(ordered):
        more = len(reports) - len(ordered)
        text_lines.append(f"…and {more} more in the app.")
        rows.append(f'<tr><td style="padding:10px 0;color:#6b7280;font-size:13px;">…and {more} more in the app.</td></tr>')
    if not has_urgent:
        text_lines.append("Nothing here needed an immediate alert; these are the day's lower-priority changes.")
    text_lines += ["", f"Change recipients: {settings_url}"]
    page = _layout(heading=f"Daily digest — {team_name}", intro=intro, body_rows="".join(rows),
                   footer=_footer_html(team_name, settings_url))
    return EmailContent(subject=subject, text="\n".join(text_lines).strip() + "\n", html=page)


def build_alert_email(*, team_name: str, workspace_name: str, workspace_id: object, app_url: str,
                      report: ReportLike) -> EmailContent:
    """Immediate alert for one critical/high card."""
    url = report_url(app_url, workspace_id, report.id)
    settings_url = f"{app_url.rstrip('/')}/w/{workspace_id}/settings"
    sev = report.severity
    subject = f"[{sev.capitalize()}] {report.title}"
    text = "\n".join([
        f"SignalLens alert for {team_name} — {workspace_name}", "",
        report.title,
        f"{sev.capitalize()} · {_evidence(report)}" + (f" · {report.change_label}" if report.change_label else ""), "",
        f"What changed: {short(report.what_changed, 600)}",
        f"Why it matters: {short(report.why_it_matters, 600)}", "",
        f"Open the card: {url}", "",
        f"Change recipients: {settings_url}",
    ]) + "\n"
    rows = (_card_html(report, url)
            + f'<tr><td style="padding:4px 0 10px;color:#374151;font-size:14px;line-height:20px;">'
              f'<span style="color:#6b7280;">What changed:</span> {html.escape(short(report.what_changed, 600))}'
              '</td></tr>')
    page = _layout(heading=f"{sev.capitalize()} alert — {team_name}", intro=workspace_name, body_rows=rows,
                   footer=_footer_html(team_name, settings_url))
    return EmailContent(subject=subject, text=text, html=page)


def build_test_email(*, team_name: str, workspace_name: str, provider_label: str, app_url: str,
                     workspace_id: object) -> EmailContent:
    settings_url = f"{app_url.rstrip('/')}/w/{workspace_id}/settings"
    subject = f"SignalLens test email for {team_name}"
    text = (f"This is a test email from SignalLens ({workspace_name}).\n\n"
            f"Email delivery works via {provider_label}. The {team_name} team will receive immediate alerts for "
            f"critical and high severity changes and a daily digest of everything else.\n\n"
            f"Change recipients: {settings_url}\n")
    rows = ('<tr><td style="padding:8px 0;color:#374151;font-size:14px;line-height:20px;">'
            f"Email delivery works via <strong>{html.escape(provider_label)}</strong>. The "
            f"{html.escape(team_name)} team will receive immediate alerts for critical and high severity changes "
            "and a daily digest of everything else.</td></tr>")
    page = _layout(heading="Test email", intro=workspace_name, body_rows=rows,
                   footer=_footer_html(team_name, settings_url))
    return EmailContent(subject=subject, text=text, html=page)
