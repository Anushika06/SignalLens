"""Outbound email through one of three interchangeable providers.

* **Brevo** (transactional API, ``POST https://api.brevo.com/v3/smtp/email``, header
  ``api-key``). Free tier: 300 emails a day. The sender address must be a verified sender
  (or on a verified domain) in the Brevo account.
* **Resend** (``POST https://api.resend.com/emails``, ``Authorization: Bearer``). Without a
  verified domain it can only send from ``onboarding@resend.dev`` to the account owner.
* **SMTP** (stdlib ``smtplib`` in a worker thread; implicit TLS on port 465, STARTTLS on 587
  and opportunistic STARTTLS elsewhere).

The HTTP-API providers matter in practice: many free hosts block outbound SMTP ports, so
an HTTPS API is the only way mail leaves the box.

``settings.email_provider`` picks one (``auto`` = Brevo if ``BREVO_API_KEY``, else Resend if
``RESEND_API_KEY``, else SMTP if ``SL_SMTP_HOST``). Senders never raise for delivery
problems: :meth:`EmailSender.send` returns a :class:`SendResult` with the error, so callers
can record it next to the notification.
"""

from __future__ import annotations

import asyncio
import logging
import re
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr, make_msgid
from typing import Protocol

import httpx

from signallens.config import Settings

__all__ = [
    "BrevoSender",
    "EmailSender",
    "EmailStatus",
    "ResendSender",
    "SendResult",
    "SmtpSender",
    "build_email_sender",
    "email_status",
    "is_valid_email",
    "normalize_emails",
]

log = logging.getLogger(__name__)

BREVO_URL = "https://api.brevo.com/v3/smtp/email"
RESEND_URL = "https://api.resend.com/emails"
RESEND_TEST_SENDER = "onboarding@resend.dev"
PROVIDER_LABELS = {"brevo": "Brevo", "resend": "Resend", "smtp": "SMTP"}
MAX_RECIPIENTS = 50

# Deliberately simple: one "@", no whitespace or list separators, a dot in the domain.
_EMAIL_RE = re.compile(r"^[^@\s<>()\[\],;:\"]+@[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?)+$")


def is_valid_email(address: str) -> bool:
    address = address.strip()
    return 3 <= len(address) <= 254 and bool(_EMAIL_RE.match(address))


def normalize_emails(addresses: list[str] | None) -> list[str]:
    """Trim, drop blanks and case-insensitive duplicates; raise ``ValueError`` on a bad address."""
    out: list[str] = []
    seen: set[str] = set()
    for raw in addresses or []:
        address = (raw or "").strip()
        if not address:
            continue
        if not is_valid_email(address):
            raise ValueError(f"{address!r} is not a valid email address")
        if address.lower() not in seen:
            seen.add(address.lower())
            out.append(address)
    if len(out) > MAX_RECIPIENTS:
        raise ValueError(f"at most {MAX_RECIPIENTS} email recipients per team")
    return out


@dataclass
class SendResult:
    ok: bool
    provider: str
    message_id: str | None = None
    error: str | None = None


class EmailSender(Protocol):
    name: str  # "brevo" | "resend" | "smtp"
    sender: str  # the From address

    async def send(self, *, to: list[str], subject: str, text: str, html: str | None = None) -> SendResult: ...


def _api_error(resp: httpx.Response) -> str:
    detail = ""
    try:
        body = resp.json()
        if isinstance(body, dict):
            detail = str(body.get("message") or body.get("error") or body.get("code") or "")
    except ValueError:
        detail = resp.text[:200]
    return f"HTTP {resp.status_code}" + (f": {detail}" if detail else "")


class _HttpSender:
    name = ""

    def __init__(self, *, sender: str, sender_name: str, timeout_s: float = 20.0,
                 http: httpx.AsyncClient | None = None) -> None:
        self.sender = sender
        self.sender_name = sender_name
        self.timeout_s = timeout_s
        self._http = http

    async def _post(self, url: str, *, headers: dict[str, str], json: dict) -> httpx.Response:
        if self._http is not None:
            return await self._http.post(url, headers=headers, json=json, timeout=self.timeout_s)
        async with httpx.AsyncClient(timeout=self.timeout_s) as client:
            return await client.post(url, headers=headers, json=json)


class BrevoSender(_HttpSender):
    name = "brevo"

    def __init__(self, api_key: str, **kw) -> None:
        super().__init__(**kw)
        self._key = api_key

    async def send(self, *, to: list[str], subject: str, text: str, html: str | None = None) -> SendResult:
        if not to:
            return SendResult(False, self.name, error="no recipients")
        payload: dict = {
            "sender": {"name": self.sender_name, "email": self.sender},
            "to": [{"email": a} for a in to],
            "subject": subject,
            "textContent": text,
        }
        if html:
            payload["htmlContent"] = html
        try:
            resp = await self._post(BREVO_URL, json=payload, headers={
                "api-key": self._key, "accept": "application/json", "content-type": "application/json"})
        except httpx.HTTPError as e:
            return SendResult(False, self.name, error=f"Brevo request failed: {type(e).__name__}: {e}")
        if resp.status_code >= 300:
            return SendResult(False, self.name, error=f"Brevo rejected the email ({_api_error(resp)})")
        try:
            message_id = resp.json().get("messageId")
        except ValueError:
            message_id = None
        return SendResult(True, self.name, message_id=message_id)


class ResendSender(_HttpSender):
    name = "resend"

    def __init__(self, api_key: str, **kw) -> None:
        super().__init__(**kw)
        self._key = api_key

    async def send(self, *, to: list[str], subject: str, text: str, html: str | None = None) -> SendResult:
        if not to:
            return SendResult(False, self.name, error="no recipients")
        payload: dict = {"from": formataddr((self.sender_name, self.sender)), "to": list(to), "subject": subject,
                         "text": text}
        if html:
            payload["html"] = html
        try:
            resp = await self._post(RESEND_URL, json=payload, headers={
                "Authorization": f"Bearer {self._key}", "content-type": "application/json"})
        except httpx.HTTPError as e:
            return SendResult(False, self.name, error=f"Resend request failed: {type(e).__name__}: {e}")
        if resp.status_code >= 300:
            return SendResult(False, self.name, error=f"Resend rejected the email ({_api_error(resp)})")
        try:
            message_id = resp.json().get("id")
        except ValueError:
            message_id = None
        return SendResult(True, self.name, message_id=message_id)


class SmtpSender:
    name = "smtp"

    def __init__(self, *, host: str, port: int, user: str | None, password: str | None, sender: str,
                 sender_name: str, timeout_s: float = 20.0) -> None:
        self.host, self.port, self.user, self.password = host, port, user, password
        self.sender, self.sender_name, self.timeout_s = sender, sender_name, timeout_s

    def build_message(self, *, to: list[str], subject: str, text: str, html: str | None) -> EmailMessage:
        msg = EmailMessage()
        msg["From"] = formataddr((self.sender_name, self.sender))
        msg["To"] = ", ".join(to)
        msg["Subject"] = subject
        msg["Message-ID"] = make_msgid(domain=self.sender.rsplit("@", 1)[-1])
        msg.set_content(text)
        if html:
            msg.add_alternative(html, subtype="html")
        return msg

    def _send_sync(self, msg: EmailMessage) -> None:
        context = ssl.create_default_context()
        if self.port == 465:
            smtp: smtplib.SMTP = smtplib.SMTP_SSL(self.host, self.port, timeout=self.timeout_s, context=context)
        else:
            smtp = smtplib.SMTP(self.host, self.port, timeout=self.timeout_s)
        with smtp:
            if self.port != 465:
                smtp.ehlo()
                # Port 587 is the submission port: never send credentials or mail in clear text there.
                if self.port == 587 or smtp.has_extn("starttls"):
                    smtp.starttls(context=context)
                    smtp.ehlo()
            if self.user:
                smtp.login(self.user, self.password or "")
            smtp.send_message(msg)

    async def send(self, *, to: list[str], subject: str, text: str, html: str | None = None) -> SendResult:
        if not to:
            return SendResult(False, self.name, error="no recipients")
        msg = self.build_message(to=to, subject=subject, text=text, html=html)
        try:
            await asyncio.to_thread(self._send_sync, msg)
        except (smtplib.SMTPException, OSError, ssl.SSLError) as e:
            return SendResult(False, self.name, error=f"SMTP delivery failed: {type(e).__name__}: {e}")
        return SendResult(True, self.name, message_id=str(msg["Message-ID"]))


# --------------------------------------------------------------------------- selection


@dataclass(frozen=True)
class EmailStatus:
    provider: str | None  # "brevo" | "resend" | "smtp" | None
    configured: bool
    sender: str | None  # From address (not a secret)
    reason: str | None = None  # why it is not configured

    @property
    def label(self) -> str:
        return PROVIDER_LABELS.get(self.provider or "", "not configured") if self.configured else "not configured"


def _choose(settings: Settings) -> tuple[str | None, str | None]:
    """(provider, problem). ``provider`` is the one selected; ``problem`` says why it can't send."""
    choice = settings.email_provider
    if choice == "none":
        return None, "Email is turned off (SL_EMAIL_PROVIDER=none)."
    has = {"brevo": bool(settings.brevo_api_key), "resend": bool(settings.resend_api_key),
           "smtp": bool(settings.smtp_host)}
    if choice == "auto":
        choice = next((name for name in ("brevo", "resend", "smtp") if has[name]), None)
        if choice is None:
            return None, "No email provider is configured (set BREVO_API_KEY, RESEND_API_KEY or SL_SMTP_HOST)."
    elif not has[choice]:
        env = {"brevo": "BREVO_API_KEY", "resend": "RESEND_API_KEY", "smtp": "SL_SMTP_HOST"}[choice]
        return choice, f"SL_EMAIL_PROVIDER={choice} but {env} is not set."
    if choice == "brevo" and not _sender(settings, choice):
        return choice, "Set SL_EMAIL_FROM to a sender address verified in your Brevo account."
    if choice == "smtp" and not _sender(settings, choice):
        return choice, "Set SL_EMAIL_FROM (or SL_SMTP_FROM) to the address mail is sent from."
    return choice, None


def _sender(settings: Settings, provider: str) -> str | None:
    if provider == "smtp":
        return settings.email_from or settings.smtp_from or (
            settings.smtp_user if settings.smtp_user and "@" in settings.smtp_user else None)
    if provider == "resend":
        return settings.email_from or settings.smtp_from or RESEND_TEST_SENDER
    return settings.email_from or settings.smtp_from


def email_status(settings: Settings) -> EmailStatus:
    provider, problem = _choose(settings)
    sender = _sender(settings, provider) if provider else None
    return EmailStatus(provider=provider, configured=provider is not None and problem is None, sender=sender,
                       reason=problem)


def build_email_sender(settings: Settings) -> EmailSender | None:
    """The configured sender, or ``None`` when email is not (fully) configured."""
    status = email_status(settings)
    if not status.configured or status.sender is None:
        return None
    common = {"sender": status.sender, "sender_name": settings.email_from_name}
    if status.provider == "brevo":
        return BrevoSender(settings.brevo_api_key or "", **common)
    if status.provider == "resend":
        return ResendSender(settings.resend_api_key or "", **common)
    return SmtpSender(host=settings.smtp_host or "", port=settings.smtp_port, user=settings.smtp_user,
                      password=settings.smtp_password, **common)
