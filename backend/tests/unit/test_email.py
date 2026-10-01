"""Email providers (Brevo, Resend, SMTP), provider selection and the digest/alert bodies."""

from __future__ import annotations

import json
import smtplib
import uuid
from types import SimpleNamespace

import httpx
import pytest
import respx

from signallens.config import Settings
from signallens.notify import email as email_mod
from signallens.notify.content import build_alert_email, build_digest_email, report_url, short, summary_line
from signallens.notify.email import (
    BREVO_URL,
    RESEND_URL,
    BrevoSender,
    ResendSender,
    SmtpSender,
    build_email_sender,
    email_status,
    normalize_emails,
)


def settings(**kw) -> Settings:
    base = {"brevo_api_key": None, "resend_api_key": None, "smtp_host": None, "email_from": None, "smtp_from": None,
            "smtp_user": None, "email_provider": "auto"}
    return Settings(_env_file=None, **{**base, **kw})


# --------------------------------------------------------------------------- addresses


def test_normalize_emails_trims_and_dedupes():
    assert normalize_emails([" a@x.com ", "A@X.com", "", "b.c+tag@sub.example.in"]) == ["a@x.com", "b.c+tag@sub.example.in"]
    assert normalize_emails(None) == []


@pytest.mark.parametrize("bad", ["nope", "a@b", "a b@c.com", "a@b..com", "x@-bad.com", "a@b.com, c@d.com", "<a@b.com>"])
def test_normalize_emails_rejects_bad_addresses(bad):
    with pytest.raises(ValueError):
        normalize_emails([bad])


# --------------------------------------------------------------------------- selection


def test_auto_prefers_brevo_then_resend_then_smtp():
    st = email_status(settings(brevo_api_key="k", resend_api_key="r", smtp_host="smtp.x", email_from="me@x.com"))
    assert (st.provider, st.configured, st.label) == ("brevo", True, "Brevo")
    st = email_status(settings(resend_api_key="r", smtp_host="smtp.x"))
    assert (st.provider, st.configured, st.sender) == ("resend", True, "onboarding@resend.dev")
    st = email_status(settings(smtp_host="smtp.x", smtp_from="bot@x.com"))
    assert (st.provider, st.configured, st.sender) == ("smtp", True, "bot@x.com")
    assert isinstance(build_email_sender(settings(smtp_host="smtp.x", smtp_from="bot@x.com")), SmtpSender)


def test_not_configured_reasons():
    st = email_status(settings())
    assert not st.configured and st.provider is None and "BREVO_API_KEY" in st.reason and st.label == "not configured"
    st = email_status(settings(brevo_api_key="k"))  # Brevo needs a verified sender
    assert st.provider == "brevo" and not st.configured and "SL_EMAIL_FROM" in st.reason
    assert build_email_sender(settings(brevo_api_key="k")) is None
    st = email_status(settings(email_provider="resend", brevo_api_key="k", email_from="me@x.com"))
    assert not st.configured and "RESEND_API_KEY" in st.reason
    st = email_status(settings(email_provider="none", brevo_api_key="k", email_from="me@x.com"))
    assert not st.configured and st.provider is None


def test_status_never_contains_the_key():
    st = email_status(settings(brevo_api_key="xkeysib-secret", email_from="me@x.com"))
    assert "xkeysib-secret" not in repr(st)


# --------------------------------------------------------------------------- Brevo / Resend


@respx.mock
async def test_brevo_sends_html_and_text():
    route = respx.post(BREVO_URL).mock(return_value=httpx.Response(201, json={"messageId": "<abc@smtp-relay>"}))
    sender = BrevoSender("brevo-key", sender="alerts@acme.in", sender_name="SignalLens")
    result = await sender.send(to=["a@x.com", "b@x.com"], subject="Hi", text="plain", html="<p>html</p>")
    assert result.ok and result.provider == "brevo" and result.message_id == "<abc@smtp-relay>"
    req = route.calls.last.request
    assert req.headers["api-key"] == "brevo-key"
    body = json.loads(req.content)
    assert body == {"sender": {"name": "SignalLens", "email": "alerts@acme.in"},
                    "to": [{"email": "a@x.com"}, {"email": "b@x.com"}], "subject": "Hi",
                    "textContent": "plain", "htmlContent": "<p>html</p>"}


@respx.mock
async def test_brevo_error_is_reported_not_raised():
    respx.post(BREVO_URL).mock(return_value=httpx.Response(
        400, json={"code": "invalid_parameter", "message": "sender is not valid"}))
    result = await BrevoSender("k", sender="x@y.com", sender_name="S").send(to=["a@x.com"], subject="s", text="t")
    assert not result.ok and "HTTP 400" in result.error and "sender is not valid" in result.error


@respx.mock
async def test_brevo_network_failure():
    respx.post(BREVO_URL).mock(side_effect=httpx.ConnectError("boom"))
    result = await BrevoSender("k", sender="x@y.com", sender_name="S").send(to=["a@x.com"], subject="s", text="t")
    assert not result.ok and "ConnectError" in result.error


@respx.mock
async def test_resend_sends_with_bearer_token():
    route = respx.post(RESEND_URL).mock(return_value=httpx.Response(200, json={"id": "re_123"}))
    sender = ResendSender("re_key", sender="onboarding@resend.dev", sender_name="SignalLens")
    result = await sender.send(to=["a@x.com"], subject="Hi", text="plain", html="<b>x</b>")
    assert result.ok and result.message_id == "re_123"
    req = route.calls.last.request
    assert req.headers["authorization"] == "Bearer re_key"
    body = json.loads(req.content)
    assert body["from"] == "SignalLens <onboarding@resend.dev>" and body["to"] == ["a@x.com"]
    assert body["html"] == "<b>x</b>" and body["text"] == "plain"


@respx.mock
async def test_resend_error():
    respx.post(RESEND_URL).mock(return_value=httpx.Response(
        403, json={"statusCode": 403, "name": "validation_error", "message": "You can only send testing emails to your own email address"}))
    result = await ResendSender("k", sender="onboarding@resend.dev", sender_name="S").send(
        to=["a@x.com"], subject="s", text="t")
    assert not result.ok and "only send testing emails" in result.error


async def test_no_recipients_is_an_error_without_a_request():
    result = await BrevoSender("k", sender="x@y.com", sender_name="S").send(to=[], subject="s", text="t")
    assert not result.ok and result.error == "no recipients"


# --------------------------------------------------------------------------- SMTP


class FakeSMTP:
    instances: list[FakeSMTP] = []
    fail_with: Exception | None = None

    def __init__(self, host, port, timeout=None, context=None):
        self.host, self.port, self.ssl = host, port, context is not None and port == 465
        self.calls: list[str] = []
        self.sent = []
        FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.calls.append("quit")

    def ehlo(self):
        self.calls.append("ehlo")

    def has_extn(self, name):
        return name == "starttls"

    def starttls(self, context=None):
        self.calls.append("starttls")

    def login(self, user, password):
        self.calls.append(f"login:{user}")

    def send_message(self, msg):
        if FakeSMTP.fail_with:
            raise FakeSMTP.fail_with
        self.sent.append(msg)


@pytest.fixture
def fake_smtp(monkeypatch):
    FakeSMTP.instances, FakeSMTP.fail_with = [], None
    monkeypatch.setattr(email_mod.smtplib, "SMTP", FakeSMTP)
    monkeypatch.setattr(email_mod.smtplib, "SMTP_SSL", FakeSMTP)
    return FakeSMTP


async def test_smtp_starttls_on_587(fake_smtp):
    sender = SmtpSender(host="smtp.x", port=587, user="u@x.com", password="p", sender="bot@x.com", sender_name="SL")
    result = await sender.send(to=["a@x.com", "b@x.com"], subject="Digest", text="plain", html="<p>rich</p>")
    assert result.ok and result.provider == "smtp" and result.message_id
    smtp = fake_smtp.instances[-1]
    assert smtp.calls[:3] == ["ehlo", "starttls", "ehlo"] and "login:u@x.com" in smtp.calls
    msg = smtp.sent[0]
    assert msg["To"] == "a@x.com, b@x.com" and msg["From"] == "SL <bot@x.com>" and msg["Subject"] == "Digest"
    assert msg.is_multipart()
    kinds = [part.get_content_type() for part in msg.iter_parts()]
    assert kinds == ["text/plain", "text/html"]


async def test_smtp_ssl_on_465(fake_smtp):
    sender = SmtpSender(host="smtp.x", port=465, user=None, password=None, sender="bot@x.com", sender_name="SL")
    assert (await sender.send(to=["a@x.com"], subject="s", text="t")).ok
    smtp = fake_smtp.instances[-1]
    assert smtp.ssl and "starttls" not in smtp.calls and not any(c.startswith("login") for c in smtp.calls)


async def test_smtp_failure_is_reported(fake_smtp):
    fake_smtp.fail_with = smtplib.SMTPRecipientsRefused({"a@x.com": (550, b"no such user")})
    sender = SmtpSender(host="smtp.x", port=587, user=None, password=None, sender="bot@x.com", sender_name="SL")
    result = await sender.send(to=["a@x.com"], subject="s", text="t")
    assert not result.ok and "SMTPRecipientsRefused" in result.error


# --------------------------------------------------------------------------- bodies


def card(severity: str, title: str, *, evidence="confirmed", why="It matters.") -> SimpleNamespace:
    return SimpleNamespace(id=uuid.uuid4(), title=title, severity=severity, evidence_status=evidence,
                           change_label="Pricing change", why_it_matters=why, what_changed="Fee went from 2% to 1.8%.")


def test_summary_line():
    reports = [card("medium", "a"), card("high", "b"), card("medium", "c")]
    assert summary_line(reports) == "3 new changes, 1 high, 2 medium"
    assert summary_line([card("low", "x")]) == "1 new change, 1 low"


def test_short_cuts_at_a_word_boundary():
    text = "word " * 100
    out = short(text, 40)
    assert out.endswith("…") and len(out) <= 41 and "  " not in out


def test_digest_groups_by_severity_and_links_to_cards():
    wid = uuid.uuid4()
    low = card("low", "Docs page updated", evidence="single_source")
    high = card("high", "Nimbus Pay cuts its fee <script>alert(1)</script>", why="x " * 400)
    med = card("medium", "New partner page")
    mail = build_digest_email(team_name="Product", workspace_name="Payments landscape", workspace_id=wid,
                              app_url="https://app.signallens.test/", reports=[low, high, med])
    assert mail.subject == "SignalLens digest for Product: 3 new changes, 1 high, 1 medium, 1 low"
    # severity order: high, then medium, then low
    t = mail.text
    assert t.index("== HIGH (1) ==") < t.index("== MEDIUM (1) ==") < t.index("== LOW (1) ==")
    assert t.index("Nimbus Pay cuts") < t.index("New partner page") < t.index("Docs page updated")
    url = f"https://app.signallens.test/w/{wid}/intel/{high.id}"
    assert url == report_url("https://app.signallens.test/", wid, high.id)
    assert url in t and url in mail.html
    assert "Single source" in t and "Confirmed" in mail.html
    # model/page text is escaped in HTML; "why it matters" is kept to a couple of lines
    assert "<script>" not in mail.html and "&lt;script&gt;" in mail.html
    why_line = next(line for line in t.splitlines() if line.strip().startswith("Why it matters: x"))
    assert len(why_line) < 300


def test_alert_email():
    wid = uuid.uuid4()
    r = card("critical", "Regulator suspends Nimbus Pay")
    mail = build_alert_email(team_name="Compliance", workspace_name="W", workspace_id=wid,
                             app_url="http://localhost:3000", report=r)
    assert mail.subject == "[Critical] Regulator suspends Nimbus Pay"
    assert f"http://localhost:3000/w/{wid}/intel/{r.id}" in mail.text
    assert "Fee went from 2% to 1.8%." in mail.html
