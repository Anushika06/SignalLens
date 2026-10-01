"""Single sign-on (OpenID Connect) against a fake identity provider.

Discovery, token and JWKS endpoints are mocked with respx; ID tokens are signed with an RSA key
generated for the test run, so signature validation is real.
"""

from __future__ import annotations

import base64
import hashlib
import time
import uuid
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import httpx
import jwt
import pytest
import respx
from cryptography.hazmat.primitives.asymmetric import rsa
from sqlalchemy import select

from signallens.api.app import create_app
from signallens.api.routes import sso
from signallens.config import Settings
from signallens.db.models import User
from signallens.runtime.services import build_services
from tests.conftest import TEST_DB

pytestmark = pytest.mark.db

ISSUER = "https://idp.test"
CLIENT_ID = "signallens-client"
APP_URL = "http://app.test"
KID = "test-key-1"
_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _jwks() -> dict:
    jwk = jwt.algorithms.RSAAlgorithm.to_jwk(_KEY.public_key(), as_dict=True)
    return {"keys": [{**jwk, "kid": KID, "alg": "RS256", "use": "sig"}]}


class FakeIdP:
    """Answers the token request with an ID token for ``claims`` (overridable per test)."""

    def __init__(self) -> None:
        self.claims: dict = {"sub": "user-123", "email": "ana@orbit.test", "email_verified": True, "name": "Ana Rao"}
        self.overrides: dict = {}
        self.nonce: str | None = None
        self.challenge: str | None = None
        self.token_requests: list[dict] = []

    def id_token(self) -> str:
        now = int(time.time())
        claims = {"iss": ISSUER, "aud": CLIENT_ID, "iat": now, "exp": now + 300, "nonce": self.nonce,
                  **self.claims, **self.overrides}
        return jwt.encode(claims, _KEY, algorithm="RS256", headers={"kid": KID})

    def token(self, request: httpx.Request) -> httpx.Response:
        form = {k: v[0] for k, v in parse_qs(request.content.decode()).items()}
        self.token_requests.append(form)
        verifier = form.get("code_verifier", "")
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        if (form.get("grant_type") != "authorization_code" or form.get("client_secret") != "s3cret"
                or challenge != self.challenge or form.get("redirect_uri") != f"{APP_URL}/api/auth/sso/callback"):
            return httpx.Response(400, json={"error": "invalid_grant"})
        return httpx.Response(200, json={"access_token": "at", "token_type": "Bearer", "id_token": self.id_token()})


def make_settings(**overrides) -> Settings:
    base = dict(env="test", database_url=TEST_DB, secret_key="test-secret-key-for-signallens-tests-000",
                public_app_url=APP_URL, oidc_issuer=ISSUER, oidc_client_id=CLIENT_ID, oidc_client_secret="s3cret",
                oidc_provider_name="Google", oidc_allowed_domains="")
    return Settings(**{**base, **overrides})


@pytest.fixture
async def sso_env(session_factory):
    sso.clear_caches()
    idp = FakeIdP()
    clients: list[httpx.AsyncClient] = []

    def client_for(**settings_overrides) -> httpx.AsyncClient:
        svc = build_services(make_settings(**settings_overrides), session_factory, use_real_providers=False)
        c = httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(svc.settings, services=svc)),
                              base_url="http://test")
        clients.append(c)
        return c

    with respx.mock(assert_all_called=False) as router:
        router.get(f"{ISSUER}/.well-known/openid-configuration").respond(200, json={
            "issuer": ISSUER, "authorization_endpoint": f"{ISSUER}/authorize", "token_endpoint": f"{ISSUER}/token",
            "jwks_uri": f"{ISSUER}/jwks"})
        router.get(f"{ISSUER}/jwks").respond(200, json=_jwks())
        router.post(f"{ISSUER}/token").mock(side_effect=idp.token)
        yield SimpleNamespace(idp=idp, client=client_for(), client_for=client_for, sf=session_factory)
    for c in clients:
        await c.aclose()
    sso.clear_caches()


async def sign_in(env, client: httpx.AsyncClient, next_path: str | None = "/w/abc", state: str | None = None):
    """Run start → (provider) → callback. Returns the callback's redirect target."""
    params = {"next": next_path} if next_path is not None else {}
    start = await client.get("/api/auth/sso/start", params=params)
    assert start.status_code == 302, start.text
    auth_url = urlsplit(start.headers["location"])
    assert f"{auth_url.scheme}://{auth_url.netloc}{auth_url.path}" == f"{ISSUER}/authorize"
    q = {k: v[0] for k, v in parse_qs(auth_url.query).items()}
    assert q["response_type"] == "code" and q["scope"] == "openid email profile"
    assert q["client_id"] == CLIENT_ID and q["code_challenge_method"] == "S256"
    assert q["redirect_uri"] == f"{APP_URL}/api/auth/sso/callback"
    env.idp.nonce, env.idp.challenge = q["nonce"], q["code_challenge"]
    cb = await client.get("/api/auth/sso/callback", params={"code": "auth-code", "state": state or q["state"]})
    assert cb.status_code == 302, cb.text
    return cb.headers["location"]


async def test_config_reports_provider(sso_env):
    assert (await sso_env.client.get("/api/auth/sso/config")).json() == {"enabled": True, "provider_name": "Google"}
    off = sso_env.client_for(oidc_issuer=None)
    assert (await off.get("/api/auth/sso/config")).json()["enabled"] is False
    start = await off.get("/api/auth/sso/start")
    assert start.status_code == 302 and start.headers["location"] == f"{APP_URL}/login?sso_error=not_configured"


async def test_new_user_is_created_and_signed_in(sso_env):
    c = sso_env.client
    assert await sign_in(sso_env, c, "/w/abc?tab=x") == f"{APP_URL}/w/abc?tab=x"
    me = (await c.get("/api/auth/me")).json()
    assert me["user"]["email"] == "ana@orbit.test" and me["user"]["name"] == "Ana Rao"
    async with sso_env.sf() as s:
        user = (await s.execute(select(User).where(User.email == "ana@orbit.test"))).scalar_one()
    assert user.auth_provider == "oidc" and user.password_hash is None and user.sso_subject == f"{ISSUER}|user-123"
    # A password sign-in is refused with a pointer to SSO.
    r = await c.post("/api/auth/login", json={"email": "ana@orbit.test", "password": "whatever-123"})
    assert r.status_code == 400 and "single sign-on" in r.json()["detail"]
    # Signing in again finds the same account by subject.
    c.cookies.clear()
    await sign_in(sso_env, c)
    assert (await c.get("/api/auth/me")).json()["user"]["id"] == str(user.id)


async def test_existing_password_account_is_linked_by_email(sso_env):
    c = sso_env.client
    signup = await c.post("/api/auth/signup", json={"email": "ana@orbit.test", "password": "password123",
                                                    "name": "Ana", "org_name": "Orbit"})
    assert signup.status_code == 200
    uid = signup.json()["user"]["id"]
    c.cookies.clear()
    await sign_in(sso_env, c)
    assert (await c.get("/api/auth/me")).json()["user"]["id"] == uid
    async with sso_env.sf() as s:
        user = await s.get(User, uuid.UUID(uid))
    assert user.sso_subject == f"{ISSUER}|user-123" and user.auth_provider == "password"
    # The password keeps working.
    c.cookies.clear()
    assert (await c.post("/api/auth/login", json={"email": "ana@orbit.test", "password": "password123"})).status_code == 200


async def test_bad_state_is_rejected(sso_env):
    c = sso_env.client
    assert await sign_in(sso_env, c, state="forged-state") == f"{APP_URL}/login?sso_error=invalid_state"
    assert (await c.get("/api/auth/me")).status_code == 401
    # No state cookie at all (e.g. a callback replayed in another browser).
    fresh = sso_env.client_for()
    cb = await fresh.get("/api/auth/sso/callback", params={"code": "x", "state": "y"})
    assert cb.headers["location"] == f"{APP_URL}/login?sso_error=invalid_state"
    assert sso_env.idp.token_requests == []


async def test_wrong_audience_is_rejected(sso_env):
    sso_env.idp.overrides = {"aud": "someone-elses-client"}
    assert await sign_in(sso_env, sso_env.client) == f"{APP_URL}/login?sso_error=invalid_token"
    assert (await sso_env.client.get("/api/auth/me")).status_code == 401


async def test_wrong_nonce_and_unverified_email_are_rejected(sso_env):
    sso_env.idp.overrides = {"nonce": "replayed"}
    assert await sign_in(sso_env, sso_env.client) == f"{APP_URL}/login?sso_error=invalid_token"
    sso_env.idp.overrides = {"email_verified": False}
    assert await sign_in(sso_env, sso_env.client) == f"{APP_URL}/login?sso_error=email_unverified"


async def test_disallowed_domain_is_rejected(sso_env):
    c = sso_env.client_for(oidc_allowed_domains="acme.test, @Example.org")
    assert await sign_in(sso_env, c) == f"{APP_URL}/login?sso_error=domain_not_allowed"
    assert (await c.get("/api/auth/me")).status_code == 401
    async with sso_env.sf() as s:
        assert (await s.execute(select(User))).scalars().all() == []
    sso_env.idp.claims["email"] = "ana@example.org"
    assert await sign_in(sso_env, c) == f"{APP_URL}/w/abc"


@pytest.mark.parametrize("target", ["https://evil.example/x", "//evil.example", "/\\evil.example", "evil",
                                    "/login?next=//evil.example", "/ok\r\nSet-Cookie: x=1"])
async def test_next_cannot_redirect_off_site(sso_env, target):
    assert await sign_in(sso_env, sso_env.client, target) == f"{APP_URL}/"


def test_safe_next():
    assert sso.safe_next("/w/1/approvals?x=1#y") == "/w/1/approvals?x=1#y"
    for bad in (None, "", "http://evil", "//evil", "/\\evil", "javascript:alert(1)", "/a\tb", "/login"):
        assert sso.safe_next(bad) == "/"
