"""Email delivery (daily digest, immediate alerts, team recipients API) and JavaScript rendering
in the collection pipeline, against the real database and pipeline code.

The outside world is simulated: a recording email sender, a fake web and a fake renderer.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy import select

from signallens.api.app import create_app
from signallens.config import Settings
from signallens.db.models import (
    Document,
    Event,
    IntelligenceReport,
    Notification,
    Organization,
    Source,
    SourceCheck,
    Team,
    Workspace,
)
from signallens.db.session import transaction
from signallens.fetch.render import RenderResult
from signallens.notify.email import SendResult
from signallens.pipeline.collection import baseline_source, check_source
from signallens.pipeline.delivery import route_report, send_digest
from signallens.runtime.services import build_services
from tests.conftest import TEST_DB
from tests.integration.fakes import FakeFetcher, FakeWayback

pytestmark = pytest.mark.db

APP_URL = "https://app.signallens.test"


class RecordingSender:
    name = "brevo"
    sender = "alerts@signallens.test"

    def __init__(self) -> None:
        self.sent: list[dict] = []
        self.fail_for: set[str] = set()  # recipient addresses whose sends fail

    async def send(self, *, to, subject, text, html=None) -> SendResult:
        self.sent.append({"to": list(to), "subject": subject, "text": text, "html": html})
        if self.fail_for & set(to):
            return SendResult(False, self.name, error="Brevo rejected the email (HTTP 400: sender is not valid)")
        return SendResult(True, self.name, message_id=f"<m{len(self.sent)}@brevo>")


def make_services(session_factory, *, pages: dict[str, str] | None = None, **settings_kw):
    # No real provider keys, whatever backend/.env says: email goes to the recording sender.
    settings = Settings(env="test", database_url=TEST_DB, secret_key="x" * 40, sandbox_enabled=False,
                        public_app_url=APP_URL, brevo_api_key=None, resend_api_key=None, smtp_host=None,
                        **settings_kw)
    svc = build_services(settings, session_factory, fetcher=FakeFetcher(pages or {}), wayback=FakeWayback({}),
                         use_real_providers=False)
    sender = RecordingSender()
    svc.extras["email_sender"] = sender
    return svc, sender


async def _workspace(s):
    org = Organization(id=uuid.uuid4(), name="Orbit")
    ws = Workspace(id=uuid.uuid4(), org_id=org.id, name="Payments landscape", status="monitoring", profile={})
    teams = SimpleNamespace(
        product=Team(id=uuid.uuid4(), workspace_id=ws.id, name="Product", areas=["pricing"],
                     emails=["neha@orbit.test", "arjun@orbit.test"]),
        compliance=Team(id=uuid.uuid4(), workspace_id=ws.id, name="Compliance", areas=["regulation"],
                        emails=["farah@orbit.test"]),
        strategy=Team(id=uuid.uuid4(), workspace_id=ws.id, name="Strategy", areas=[], emails=[]),
    )
    for row in (org, ws, teams.product, teams.compliance, teams.strategy):
        s.add(row)
        await s.flush()
    return ws, teams


async def _card(s, ws, *, title: str, severity: str, teams: list[Team], area: str = "pricing",
                evidence: str = "confirmed") -> IntelligenceReport:
    event = Event(id=uuid.uuid4(), workspace_id=ws.id, title=title, status="published", area=area,
                  event_type="pricing")
    s.add(event)
    await s.flush()
    report = IntelligenceReport(
        id=uuid.uuid4(), workspace_id=ws.id, event_id=event.id, area=area, title=title, change_label="Pricing change",
        what_changed=f"{title}.", why_it_matters=f"Why {title} matters to Orbit.", severity=severity,
        evidence_status=evidence, affected_team_ids=[str(t.id) for t in teams],
    )
    s.add(report)
    await s.flush()
    return report


async def _email_notes(sf) -> list[Notification]:
    async with sf() as s:
        return list((await s.execute(select(Notification).where(Notification.channel == "email"))).scalars())


async def test_digest_emails_each_team_once_with_its_cards(session_factory):
    svc, sender = make_services(session_factory)
    async with transaction(session_factory) as s:
        ws, teams = await _workspace(s)
        fee = await _card(s, ws, title="Nimbus Pay changes its refund policy", severity="medium", teams=[teams.product])
        faq = await _card(s, ws, title="Nimbus Pay FAQ updated", severity="low",
                          teams=[teams.product, teams.compliance], evidence="single_source")
        kyc = await _card(s, ws, title="Nimbus Pay KYC page reworded", severity="low", area="regulation",
                          teams=[teams.compliance, teams.strategy])
    for r in (fee, faq, kyc):  # medium/low: queued for the digest, nothing emailed yet
        out = await route_report(svc, r.id)
        assert out["immediate"] is False and out["emails"] == 0
    assert sender.sent == []

    result = await send_digest(svc, ws.id)
    assert result["emails_sent"] == 2 and result["emails_failed"] == 0 and result["items"] == 5

    by_to = {tuple(m["to"]): m for m in sender.sent}
    assert set(by_to) == {("neha@orbit.test", "arjun@orbit.test"), ("farah@orbit.test",)}  # Strategy has no emails
    product = by_to[("neha@orbit.test", "arjun@orbit.test")]
    assert product["subject"] == "SignalLens digest for Product: 2 new changes, 1 medium, 1 low"
    assert "refund policy" in product["text"] and "FAQ updated" in product["text"] and "KYC" not in product["text"]
    assert f"{APP_URL}/w/{ws.id}/intel/{fee.id}" in product["html"]
    assert product["text"].index("== MEDIUM") < product["text"].index("== LOW")
    compliance = by_to[("farah@orbit.test",)]
    assert "FAQ updated" in compliance["text"] and "KYC page reworded" in compliance["text"]

    notes = await _email_notes(session_factory)
    assert len(notes) == 4 and all(n.status == "sent" and n.sent_at for n in notes)
    assert {(n.team_id, n.report_id) for n in notes} == {
        (teams.product.id, fee.id), (teams.product.id, faq.id),
        (teams.compliance.id, faq.id), (teams.compliance.id, kyc.id)}

    # Idempotent: a second run (or a retried job) sends nothing more.
    again = await send_digest(svc, ws.id)
    assert again["items"] == 0 and again["emails_sent"] == 0 and len(sender.sent) == 2
    assert len(await _email_notes(session_factory)) == 4


async def test_digest_email_failure_is_recorded_and_not_retried(session_factory):
    svc, sender = make_services(session_factory)
    sender.fail_for = {"farah@orbit.test"}
    async with transaction(session_factory) as s:
        ws, teams = await _workspace(s)
        r = await _card(s, ws, title="Nimbus Pay FAQ updated", severity="low", teams=[teams.product, teams.compliance])
    await route_report(svc, r.id)
    result = await send_digest(svc, ws.id)
    assert result["emails_sent"] == 1 and result["emails_failed"] == 1
    notes = {n.team_id: n for n in await _email_notes(session_factory)}
    assert notes[teams.product.id].status == "sent"
    failed = notes[teams.compliance.id]
    assert failed.status == "failed" and "sender is not valid" in failed.error and failed.sent_at is None
    # Inbox delivery is unaffected by the email failure.
    async with session_factory() as s:
        inbox = (await s.execute(select(Notification).where(Notification.channel == "digest"))).scalars().all()
    assert len(inbox) == 2 and all(n.status == "sent" for n in inbox)
    await send_digest(svc, ws.id)
    assert len(sender.sent) == 2  # never re-sent automatically


async def test_digest_email_can_be_turned_off(session_factory):
    svc, sender = make_services(session_factory, digest_email_enabled=False)
    async with transaction(session_factory) as s:
        ws, teams = await _workspace(s)
        r = await _card(s, ws, title="Nimbus Pay FAQ updated", severity="low", teams=[teams.product])
    await route_report(svc, r.id)
    assert (await send_digest(svc, ws.id))["items"] == 1
    assert sender.sent == [] and await _email_notes(session_factory) == []


async def test_immediate_alert_emails_the_team_once(session_factory):
    svc, sender = make_services(session_factory)
    async with transaction(session_factory) as s:
        ws, teams = await _workspace(s)
        r = await _card(s, ws, title="Nimbus Pay cuts its standard fee to 1.8%", severity="high",
                        teams=[teams.product, teams.strategy])
    out = await route_report(svc, r.id)
    assert out["immediate"] is True and out["emails"] == 1
    assert len(sender.sent) == 1
    mail = sender.sent[0]
    assert mail["to"] == ["neha@orbit.test", "arjun@orbit.test"]
    assert mail["subject"] == "[High] Nimbus Pay cuts its standard fee to 1.8%"
    assert f"{APP_URL}/w/{ws.id}/intel/{r.id}" in mail["text"]
    # A retried routing job does not email again.
    await route_report(svc, r.id)
    assert len(sender.sent) == 1
    notes = await _email_notes(session_factory)
    assert [(n.team_id, n.status) for n in notes] == [(teams.product.id, "sent")]
    # High cards are not in the digest.
    assert (await send_digest(svc, ws.id))["items"] == 0 and len(sender.sent) == 1


async def test_approved_share_without_provider_is_saved(session_factory):
    from signallens.pipeline.delivery import _send_email

    svc, _ = make_services(session_factory)
    svc.extras["email_sender"] = None  # nothing configured
    result = await _send_email(svc, to="partner@else.test", subject="FYI", body="Body")
    assert result["delivered"] is False and "saved here" in result["reason"] and result["body"] == "Body"
    sender = RecordingSender()
    svc.extras["email_sender"] = sender
    result = await _send_email(svc, to="partner@else.test", subject="FYI", body="Body")
    assert result["delivered"] is True and result["provider"] == "brevo" and sender.sent[0]["to"] == ["partner@else.test"]


# --------------------------------------------------------------------------- API


@pytest.fixture
async def api(session_factory):
    svc, sender = make_services(session_factory)
    app = create_app(svc.settings, services=svc)
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")
    resp = await client.post("/api/auth/signup", json={"email": "ana@orbit.test", "password": "password123",
                                                       "name": "Ana", "org_name": "Orbit"})
    assert resp.status_code == 200, resp.text
    yield SimpleNamespace(client=client, sender=sender, svc=svc)
    await client.aclose()


async def test_team_recipients_api_and_test_email(api):
    c = api.client
    ws = (await c.post("/api/workspaces", json={"name": "W", "teams": [
        {"name": "Product", "areas": ["pricing"], "emails": [" neha@orbit.test", "NEHA@orbit.test", "arjun@orbit.test"]},
    ]})).json()
    wid, team = ws["id"], ws["teams"][0]
    assert team["emails"] == ["neha@orbit.test", "arjun@orbit.test"]

    bad = await c.post(f"/api/workspaces/{wid}/teams", json={"name": "Ops", "emails": ["not-an-email"]})
    assert bad.status_code == 422 and "not a valid email" in bad.text
    created = (await c.post(f"/api/workspaces/{wid}/teams", json={"name": "Ops", "emails": []})).json()
    assert created["emails"] == []
    nothing = await c.post(f"/api/workspaces/{wid}/teams/{created['id']}/test-email")
    assert nothing.status_code == 422

    patched = await c.patch(f"/api/workspaces/{wid}/teams/{team['id']}", json={"emails": ["lead@orbit.test"]})
    assert patched.status_code == 200 and patched.json()["emails"] == ["lead@orbit.test"]
    assert (await c.patch(f"/api/workspaces/{wid}/teams/{team['id']}", json={"emails": ["x@"]})).status_code == 422
    listed = (await c.get(f"/api/workspaces/{wid}/teams")).json()
    assert next(t for t in listed if t["id"] == team["id"])["emails"] == ["lead@orbit.test"]

    sent = (await c.post(f"/api/workspaces/{wid}/teams/{team['id']}/test-email")).json()
    assert sent == {"delivered": True, "provider": "brevo", "recipients": ["lead@orbit.test"],
                    "message_id": "<m1@brevo>", "error": None}
    assert api.sender.sent[0]["subject"] == "SignalLens test email for Product"

    api.svc.extras["email_sender"] = None
    off = (await c.post(f"/api/workspaces/{wid}/teams/{team['id']}/test-email")).json()
    assert off["delivered"] is False and off["provider"] is None and "BREVO_API_KEY" in off["error"]

    config = (await c.get("/api/system/config")).json()
    assert config["email"] == {"provider": None, "configured": False, "sender": None, "digest_enabled": True,
                               "reason": "No email provider is configured (set BREVO_API_KEY, RESEND_API_KEY or "
                                         "SL_SMTP_HOST)."}


# --------------------------------------------------------------------------- JS rendering in collection

SHELL = ('<!doctype html><html><head><title>Nimbus</title><script src="/app.js"></script></head>'
         '<body><noscript>You need to enable JavaScript to run this app.</noscript><div id="root"></div></body></html>')
RENDERED = ("<html><head><title>Nimbus Pay pricing</title></head><body><h1>Pricing</h1>"
            + "".join(f"<p>Plan {i}: a flat {i}% per successful transaction for every merchant in India.</p>"
                      for i in range(1, 6)) + "</body></html>")
URL = "https://nimbus.example/pricing"


async def _source(sf) -> uuid.UUID:
    async with transaction(sf) as s:
        org = Organization(id=uuid.uuid4(), name="Orbit")
        ws = Workspace(id=uuid.uuid4(), org_id=org.id, name="W", status="baselining", profile={})
        src = Source(id=uuid.uuid4(), workspace_id=ws.id, kind="page", url=URL, areas=["pricing"])
        for row in (org, ws, src):
            s.add(row)
            await s.flush()
        return src.id


async def test_js_shell_is_skipped_with_a_clear_reason_when_rendering_is_off(session_factory):
    svc, _ = make_services(session_factory, pages={URL: SHELL}, render_js=False)
    sid = await _source(session_factory)
    assert (await baseline_source(svc, sid))["outcome"] == "degenerate"
    async with session_factory() as s:
        check = (await s.execute(select(SourceCheck).where(SourceCheck.source_id == sid))).scalar_one()
        src = await s.get(Source, sid)
    assert check.outcome == "degenerate"
    assert check.error == "needs JavaScript rendering (disabled on this deployment)"
    assert src.config["js_rendered"] is False


async def test_js_shell_is_rendered_and_monitored_when_enabled(session_factory):
    rendered_html = {"html": RENDERED}
    calls: list[str] = []

    async def fake_renderer(url, **kw):
        calls.append(url)
        return RenderResult(html=rendered_html["html"], final_url=url, status=200)

    svc, _ = make_services(session_factory, pages={URL: SHELL}, render_js=True)
    svc.extras["renderer"] = fake_renderer
    sid = await _source(session_factory)
    assert (await baseline_source(svc, sid)) == {"outcome": "baseline", "values": 0, "rendered": True}
    async with session_factory() as s:
        doc = (await s.execute(select(Document).where(Document.url == URL))).scalar_one()
        src = await s.get(Source, sid)
    assert "Plan 3: a flat 3% per successful transaction" in doc.text
    assert doc.meta["rendered_with"] == "headless_browser" and src.config["js_rendered"] is True
    assert src.config["render_note"] == "rendered with headless browser"

    # Next check: same rendered content -> unchanged (compared on the rendered text, not the shell).
    out = await check_source(svc, sid)
    assert out["outcome"] == "unchanged" and calls == [URL, URL]
