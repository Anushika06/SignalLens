"""Single sign-on with OpenID Connect (authorization-code flow with PKCE).

Works with any OIDC provider that publishes discovery metadata: Google
(``https://accounts.google.com``), Microsoft Entra ID (``https://login.microsoftonline.com/<tenant>/v2.0``),
Okta (``https://<org>.okta.com``) and others.

The browser only ever talks to the web app's origin: ``/api/*`` is proxied to this API, so the
redirect URI is ``{public_app_url}/api/auth/sso/callback`` and the session cookie set on the
callback is first-party.

Flow: ``/start`` stores ``state``, ``nonce``, the PKCE verifier and the post-login path in a
short-lived signed cookie and redirects to the provider. ``/callback`` checks ``state``,
exchanges the code (client_secret_post), validates the ID token (signature from the provider's
JWKS, issuer, audience, expiry, nonce, verified email, allowed domains), finds or creates the
user and starts a normal session. Every failure redirects to ``/login?sso_error=<code>``.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import secrets
import time
import uuid
from datetime import timedelta
from typing import Any
from urllib.parse import urlencode

import httpx
import jwt
from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from signallens.api import schemas as S
from signallens.api.deps import session
from signallens.api.routes.auth import _set_cookie
from signallens.config import Settings
from signallens.db.base import utcnow
from signallens.db.models import Organization, User

log = logging.getLogger(__name__)
router = APIRouter(prefix="/auth/sso", tags=["auth"])

STATE_COOKIE = "sl_sso"
STATE_COOKIE_PATH = "/api/auth/sso"
STATE_TTL_S = 600
METADATA_TTL_S = 3600
ID_TOKEN_ALGORITHMS = ["RS256", "RS384", "RS512", "PS256", "PS384", "PS512", "ES256", "ES384", "ES512"]
HTTP_TIMEOUT_S = 10.0

# issuer -> (fetched_at, document); jwks_uri -> (fetched_at, PyJWKSet)
_discovery_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_jwks_cache: dict[str, tuple[float, jwt.PyJWKSet]] = {}


class SsoError(Exception):
    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(detail or code)
        self.code = code


def clear_caches() -> None:
    _discovery_cache.clear()
    _jwks_cache.clear()


# --- helpers ----------------------------------------------------------------------------------
def safe_next(raw: str | None) -> str:
    """Only same-origin relative paths: no scheme, no ``//host``, no backslashes or control chars."""
    value = (raw or "").strip()
    if (not value.startswith("/") or value.startswith("//") or "\\" in value
            or any(ord(c) < 32 or ord(c) == 127 for c in value)):
        return "/"
    if value == "/login" or value.startswith(("/login?", "/login/", "/login#")):
        return "/"
    return value


def _app_url(settings: Settings, path: str) -> str:
    return settings.public_app_url.rstrip("/") + path


def redirect_uri(settings: Settings) -> str:
    return _app_url(settings, "/api/auth/sso/callback")


def _error_redirect(settings: Settings, code: str) -> RedirectResponse:
    resp = RedirectResponse(_app_url(settings, f"/login?{urlencode({'sso_error': code})}"), status_code=302)
    resp.delete_cookie(STATE_COOKIE, path=STATE_COOKIE_PATH)
    return resp


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def pkce_challenge(verifier: str) -> str:
    return _b64url(hashlib.sha256(verifier.encode()).digest())


async def discovery(settings: Settings) -> dict[str, Any]:
    issuer = (settings.oidc_issuer or "").rstrip("/")
    hit = _discovery_cache.get(issuer)
    if hit and time.monotonic() - hit[0] < METADATA_TTL_S:
        return hit[1]
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_S) as client:
            r = await client.get(f"{issuer}/.well-known/openid-configuration")
            r.raise_for_status()
            doc = r.json()
    except (httpx.HTTPError, ValueError) as e:
        raise SsoError("provider_unavailable", f"discovery failed: {e}") from e
    for key in ("issuer", "authorization_endpoint", "token_endpoint", "jwks_uri"):
        if not isinstance(doc.get(key), str):
            raise SsoError("provider_unavailable", f"discovery document has no {key}")
    _discovery_cache[issuer] = (time.monotonic(), doc)
    return doc


async def _jwks(uri: str, *, refresh: bool = False) -> jwt.PyJWKSet:
    hit = _jwks_cache.get(uri)
    if hit and not refresh and time.monotonic() - hit[0] < METADATA_TTL_S:
        return hit[1]
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_S) as client:
            r = await client.get(uri)
            r.raise_for_status()
            keys = jwt.PyJWKSet.from_dict(r.json())
    except (httpx.HTTPError, ValueError, jwt.PyJWTError) as e:
        raise SsoError("provider_unavailable", f"JWKS fetch failed: {e}") from e
    _jwks_cache[uri] = (time.monotonic(), keys)
    return keys


async def _signing_key(uri: str, kid: str | None) -> jwt.PyJWK:
    for refresh in (False, True):  # an unknown kid means the provider rotated its keys
        keys = await _jwks(uri, refresh=refresh)
        candidates = [k for k in keys.keys if kid is None or k.key_id == kid]
        if candidates:
            return candidates[0]
    raise SsoError("invalid_token", f"no signing key with kid {kid!r}")


async def validate_id_token(settings: Settings, meta: dict[str, Any], id_token: str, nonce: str) -> dict[str, Any]:
    try:
        header = jwt.get_unverified_header(id_token)
    except jwt.PyJWTError as e:
        raise SsoError("invalid_token", f"unreadable id_token: {e}") from e
    alg = header.get("alg")
    if alg not in ID_TOKEN_ALGORITHMS:
        raise SsoError("invalid_token", f"unsupported id_token algorithm {alg!r}")
    key = await _signing_key(meta["jwks_uri"], header.get("kid"))
    try:
        claims = jwt.decode(id_token, key.key, algorithms=[alg], audience=settings.oidc_client_id,
                            issuer=meta["issuer"], leeway=60,
                            options={"require": ["iss", "aud", "exp", "iat", "sub"]})
    except jwt.PyJWTError as e:
        raise SsoError("invalid_token", f"id_token rejected: {e}") from e
    if not secrets.compare_digest(str(claims.get("nonce", "")), nonce):
        raise SsoError("invalid_token", "nonce mismatch")
    return claims


def check_email(settings: Settings, claims: dict[str, Any]) -> str:
    email = str(claims.get("email") or "").strip().lower()
    if "@" not in email:
        raise SsoError("email_missing", "the provider did not return an email address")
    verified = claims.get("email_verified")
    if verified is not None and verified is not True and str(verified).lower() != "true":
        raise SsoError("email_unverified", "email address not verified by the provider")
    allowed = settings.oidc_allowed_domain_set
    if allowed and email.rpartition("@")[2] not in allowed:
        raise SsoError("domain_not_allowed", f"{email} is outside the allowed domains")
    return email


async def find_or_create_user(s: AsyncSession, claims: dict[str, Any], email: str) -> User:
    subject = f"{claims['iss']}|{claims['sub']}"
    user = (await s.execute(select(User).where(User.sso_subject == subject))).scalar_one_or_none()
    if user is not None:
        return user
    user = (await s.execute(select(User).where(User.email == email))).scalar_one_or_none()
    if user is not None:
        if user.sso_subject and user.sso_subject != subject:
            # Same email, different identity at the provider (e.g. a deleted and re-created account).
            raise SsoError("account_conflict", f"{email} is linked to a different single sign-on identity")
        user.sso_subject = subject  # password users keep their password and auth_provider
        await s.flush()
        return user
    name = str(claims.get("name") or "").strip() or email.partition("@")[0]
    org_name = str(claims.get("hd") or "").strip() or f"{name}'s organisation"
    org = Organization(id=uuid.uuid4(), name=org_name[:200])
    user = User(id=uuid.uuid4(), org_id=org.id, email=email, name=name[:200], password_hash=None,
                auth_provider="oidc", sso_subject=subject)
    s.add_all([org, user])
    await s.flush()
    return user


# --- routes -----------------------------------------------------------------------------------
@router.get("/config", response_model=S.SsoConfig)
async def sso_config(request: Request) -> S.SsoConfig:
    settings: Settings = request.app.state.services.settings
    return S.SsoConfig(enabled=settings.sso_enabled, provider_name=settings.oidc_provider_name)


@router.get("/start")
async def sso_start(request: Request, next: str | None = None) -> RedirectResponse:
    settings: Settings = request.app.state.services.settings
    if not settings.sso_enabled:
        return _error_redirect(settings, "not_configured")
    try:
        meta = await discovery(settings)
    except SsoError as e:
        log.warning("sso start failed: %s", e)
        return _error_redirect(settings, e.code)
    state, nonce, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(32), secrets.token_urlsafe(64)
    now = utcnow()
    cookie = jwt.encode({"state": state, "nonce": nonce, "verifier": verifier, "next": safe_next(next),
                         "iat": int(now.timestamp()), "exp": int((now + timedelta(seconds=STATE_TTL_S)).timestamp())},
                        settings.secret_key, algorithm="HS256")
    params = {"response_type": "code", "client_id": settings.oidc_client_id, "redirect_uri": redirect_uri(settings),
              "scope": "openid email profile", "state": state, "nonce": nonce,
              "code_challenge": pkce_challenge(verifier), "code_challenge_method": "S256"}
    sep = "&" if "?" in meta["authorization_endpoint"] else "?"
    resp = RedirectResponse(f"{meta['authorization_endpoint']}{sep}{urlencode(params)}", status_code=302)
    resp.set_cookie(STATE_COOKIE, cookie, max_age=STATE_TTL_S, httponly=True, samesite="lax",
                    secure=settings.env == "prod", path=STATE_COOKIE_PATH)
    return resp


@router.get("/callback")
async def sso_callback(request: Request, s: AsyncSession = Depends(session), code: str | None = None,
                       state: str | None = None, error: str | None = None) -> RedirectResponse:
    settings: Settings = request.app.state.services.settings
    if not settings.sso_enabled:
        return _error_redirect(settings, "not_configured")
    if error:
        return _error_redirect(settings, "access_denied" if error == "access_denied" else "provider_error")
    try:
        raw = request.cookies.get(STATE_COOKIE)
        try:
            saved = jwt.decode(raw or "", settings.secret_key, algorithms=["HS256"])
        except jwt.PyJWTError as e:
            raise SsoError("invalid_state", f"missing or expired state cookie: {e}") from e
        if not state or not code or not secrets.compare_digest(str(saved.get("state", "")), state):
            raise SsoError("invalid_state", "state mismatch")
        meta = await discovery(settings)
        try:
            async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_S) as client:
                r = await client.post(meta["token_endpoint"], headers={"Accept": "application/json"}, data={
                    "grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri(settings),
                    "client_id": settings.oidc_client_id, "client_secret": settings.oidc_client_secret,
                    "code_verifier": saved["verifier"]})
            tokens = r.json() if r.content else {}
        except (httpx.HTTPError, ValueError) as e:
            raise SsoError("token_exchange_failed", f"token request failed: {e}") from e
        if r.status_code != 200 or not isinstance(tokens, dict) or not tokens.get("id_token"):
            raise SsoError("token_exchange_failed", f"token endpoint returned {r.status_code}")
        claims = await validate_id_token(settings, meta, str(tokens["id_token"]), str(saved.get("nonce", "")))
        email = check_email(settings, claims)
        user = await find_or_create_user(s, claims, email)
    except SsoError as e:
        log.warning("sso sign-in failed (%s): %s", e.code, e)
        return _error_redirect(settings, e.code)
    resp = RedirectResponse(_app_url(settings, safe_next(saved.get("next"))), status_code=302)
    resp.delete_cookie(STATE_COOKIE, path=STATE_COOKIE_PATH)
    _set_cookie(request, resp, user)
    return resp
