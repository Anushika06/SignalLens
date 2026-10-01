"""Workspace roles, members management and who may approve external actions."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy import func, select

from signallens.api.app import create_app
from signallens.api.security import issue_token, verify_password
from signallens.config import Settings
from signallens.db.models import Approval, User, Workspace, WorkspaceMember
from signallens.db.session import transaction
from signallens.demo import (
    DEMO_ADMIN_EMAIL,
    seed_demo_members,
    seed_demo_user,
    seed_lab_workspace,
    seed_sandbox,
)
from signallens.runtime.services import build_services
from tests.conftest import TEST_DB

pytestmark = pytest.mark.db
SECRET = "test-secret-key-for-signallens-tests-000"


@pytest.fixture
async def env(session_factory):
    settings = Settings(env="test", database_url=TEST_DB, secret_key=SECRET, oidc_issuer=None)
    svc = build_services(settings, session_factory, use_real_providers=False)
    app = create_app(settings, services=svc)
    clients: list[httpx.AsyncClient] = []

    def client(user: User | None = None) -> httpx.AsyncClient:
        c = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")
        if user is not None:
            c.cookies.set("sl_session", issue_token(user.id, user.org_id, secret=SECRET, days=1))
        clients.append(c)
        return c

    yield SimpleNamespace(client=client, sf=session_factory)
    for c in clients:
        await c.aclose()


async def ok(resp: httpx.Response, status: int = 200):
    assert resp.status_code == status, resp.text
    return resp.json() if resp.content else None


async def user_by_email(env, email: str) -> User:
    async with env.sf() as s:
        return (await s.execute(select(User).where(User.email == email))).scalar_one()


async def add_approval(env, wid: str, requested_by: uuid.UUID | None) -> str:
    async with transaction(env.sf) as s:
        a = Approval(id=uuid.uuid4(), workspace_id=uuid.UUID(wid), action_type="send_external_email",
                     title="Email the brief to counsel", payload={"to": "counsel@law.test"}, reason="test",
                     requested_by="user" if requested_by else "impact_analyst", requested_by_user_id=requested_by)
        s.add(a)
    return str(a.id)


@pytest.fixture
async def team(env):
    """Ana (owner, created the workspace), Bo (member), and the workspace id."""
    ana_c = env.client()
    await ok(await ana_c.post("/api/auth/signup", json={"email": "ana@orbit.test", "password": "password123",
                                                        "name": "Ana", "org_name": "Orbit"}))
    ws = await ok(await ana_c.post("/api/workspaces", json={"name": "Payments watch", "teams": []}))
    assert ws["my_role"] == "owner" and ws["can_approve"] is True and ws["can_manage_members"] is True
    bo = await ok(await ana_c.post(f"/api/workspaces/{ws['id']}/members", json={"email": "Bo@Orbit.test",
                                                                                 "name": "Bo"}))
    assert bo["role"] == "member" and bo["auth_provider"] == "oidc" and bo["email"] == "bo@orbit.test"
    ana, bo_user = await user_by_email(env, "ana@orbit.test"), await user_by_email(env, "bo@orbit.test")
    return SimpleNamespace(wid=ws["id"], ana=ana, bo=bo_user, ana_c=ana_c, bo_c=env.client(bo_user))


async def test_members_listing_and_adding(env, team):
    members = await ok(await team.ana_c.get(f"/api/workspaces/{team.wid}/members"))
    assert [(m["email"], m["role"], m["is_you"]) for m in members] == [
        ("ana@orbit.test", "owner", True), ("bo@orbit.test", "member", False)]
    # The invited account has no password; a password sign-in points to SSO.
    assert team.bo.password_hash is None and not verify_password("anything", team.bo.password_hash)
    r = await env.client().post("/api/auth/login", json={"email": "bo@orbit.test", "password": "anything1"})
    assert r.status_code == 400 and "single sign-on" in r.json()["detail"]
    # Duplicates, other organisations and non-managers are refused.
    await ok(await team.ana_c.post(f"/api/workspaces/{team.wid}/members", json={"email": "bo@orbit.test"}), 409)
    other = env.client()
    await ok(await other.post("/api/auth/signup", json={"email": "zed@else.test", "password": "password123",
                                                        "name": "Zed", "org_name": "Else"}))
    await ok(await team.ana_c.post(f"/api/workspaces/{team.wid}/members", json={"email": "zed@else.test"}), 409)
    await ok(await other.get(f"/api/workspaces/{team.wid}/members"), 404)
    await ok(await team.bo_c.post(f"/api/workspaces/{team.wid}/members", json={"email": "cy@orbit.test"}), 403)
    detail = await ok(await team.bo_c.get(f"/api/workspaces/{team.wid}"))
    assert detail["my_role"] == "member" and detail["can_approve"] is False


async def test_role_changes_and_last_owner_guard(env, team):
    base = f"/api/workspaces/{team.wid}/members"
    # The sole owner can't step down or leave.
    await ok(await team.ana_c.patch(f"{base}/{team.ana.id}", json={"role": "admin"}), 409)
    await ok(await team.ana_c.delete(f"{base}/{team.ana.id}"), 409)
    await ok(await team.ana_c.patch(f"{base}/{team.bo.id}", json={"role": "superuser"}), 422)
    assert (await ok(await team.ana_c.patch(f"{base}/{team.bo.id}", json={"role": "admin"})))["role"] == "admin"
    # An admin manages members but can't create owners or touch an owner.
    cy = await ok(await team.bo_c.post(base, json={"email": "cy@orbit.test"}))
    await ok(await team.bo_c.patch(f"{base}/{cy['user_id']}", json={"role": "owner"}), 403)
    await ok(await team.bo_c.patch(f"{base}/{team.ana.id}", json={"role": "member"}), 403)
    await ok(await team.bo_c.delete(f"{base}/{team.ana.id}"), 403)
    await ok(await team.bo_c.delete(f"{base}/{cy['user_id']}"), 204)
    assert "cy@orbit.test" not in [m["email"] for m in await ok(await team.ana_c.get(base))]
    await ok(await team.bo_c.delete(f"{base}/{cy['user_id']}"), 404)
    # With a second owner, Ana may step down.
    await ok(await team.ana_c.patch(f"{base}/{team.bo.id}", json={"role": "owner"}))
    assert (await ok(await team.ana_c.patch(f"{base}/{team.ana.id}", json={"role": "admin"})))["role"] == "admin"


async def test_sole_approver_may_self_approve_with_a_note(env, team):
    aid = await add_approval(env, team.wid, team.ana.id)
    [a] = await ok(await team.ana_c.get(f"/api/workspaces/{team.wid}/approvals"))
    assert a["can_decide"] is True and a["requested_by_name"] == "Ana" and a["requested_by_user_id"] == str(team.ana.id)
    decided = await ok(await team.ana_c.post(f"/api/workspaces/{team.wid}/approvals/{aid}/decide",
                                             json={"decision": "approve", "note": "fine"}))
    assert decided["status"] == "approved" and decided["decision_note"] == "fine (self-approved: sole approver)"
    assert decided["can_decide"] is False and decided["decided_by"] == "ana@orbit.test"
    aid2 = await add_approval(env, team.wid, team.ana.id)
    decided = await ok(await team.ana_c.post(f"/api/workspaces/{team.wid}/approvals/{aid2}/decide",
                                             json={"decision": "approve"}))
    assert decided["decision_note"] == "(self-approved: sole approver)"


async def test_members_cannot_decide(env, team):
    aid = await add_approval(env, team.wid, None)  # proposed by an agent
    [a] = await ok(await team.bo_c.get(f"/api/workspaces/{team.wid}/approvals"))
    assert a["can_decide"] is False and "owners and admins" in a["cannot_decide_reason"]
    assert a["requested_by_user_id"] is None and a["requested_by_name"] is None
    r = await team.bo_c.post(f"/api/workspaces/{team.wid}/approvals/{aid}/decide", json={"decision": "reject"})
    assert r.status_code == 403 and "owners and admins" in r.json()["detail"]
    # Any owner/admin may decide an agent's proposal.
    decided = await ok(await team.ana_c.post(f"/api/workspaces/{team.wid}/approvals/{aid}/decide",
                                             json={"decision": "reject", "note": "no"}))
    assert decided["status"] == "rejected" and decided["decision_note"] == "no"


async def test_requester_cannot_approve_when_another_approver_exists(env, team):
    await ok(await team.ana_c.patch(f"/api/workspaces/{team.wid}/members/{team.bo.id}", json={"role": "admin"}))
    aid = await add_approval(env, team.wid, team.ana.id)
    [a] = await ok(await team.ana_c.get(f"/api/workspaces/{team.wid}/approvals"))
    assert a["can_decide"] is False and "another owner or admin" in a["cannot_decide_reason"]
    r = await team.ana_c.post(f"/api/workspaces/{team.wid}/approvals/{aid}/decide", json={"decision": "approve"})
    assert r.status_code == 403 and "another owner or admin" in r.json()["detail"]
    [a] = await ok(await team.bo_c.get(f"/api/workspaces/{team.wid}/approvals?status=pending"))
    assert a["can_decide"] is True and a["requested_by_name"] == "Ana"
    decided = await ok(await team.bo_c.post(f"/api/workspaces/{team.wid}/approvals/{aid}/decide",
                                            json={"decision": "approve", "note": "Looks right"}))
    assert decided["status"] == "approved" and decided["decision_note"] == "Looks right"
    assert decided["decided_by"] == "bo@orbit.test"
    await ok(await team.ana_c.post(f"/api/workspaces/{team.wid}/approvals/{aid}/decide",
                                   json={"decision": "approve"}), 409)


async def test_workspace_without_owner_gets_one(env, team):
    async with transaction(env.sf) as s:
        m = await s.get(WorkspaceMember, (uuid.UUID(team.wid), team.ana.id))
        m.role = "member"
    detail = await ok(await team.bo_c.get(f"/api/workspaces/{team.wid}"))
    assert detail["my_role"] == "member"  # the earliest member (Ana) is promoted, not the visitor
    detail = await ok(await team.ana_c.get(f"/api/workspaces/{team.wid}"))
    assert detail["my_role"] == "owner"


async def test_demo_seed_roles_are_idempotent(env):
    for _ in range(2):
        async with transaction(env.sf) as s:
            org, user, _created = await seed_demo_user(s)
            await seed_sandbox(s)
            await seed_lab_workspace(s, org, user)
            meera = await seed_demo_members(s, org, user)
    async with env.sf() as s:
        assert (await s.execute(select(func.count()).select_from(User)
                                .where(User.email == DEMO_ADMIN_EMAIL))).scalar_one() == 1
        ws = (await s.execute(select(Workspace).where(Workspace.org_id == org.id))).scalar_one()
        roles = dict((await s.execute(select(WorkspaceMember.user_id, WorkspaceMember.role)
                                      .where(WorkspaceMember.workspace_id == ws.id))).all())
    assert roles == {user.id: "owner", meera.id: "admin"}
    meera_c = env.client()
    await ok(await meera_c.post("/api/auth/login", json={"email": DEMO_ADMIN_EMAIL, "password": "signallens-demo"}))
    assert (await ok(await meera_c.get(f"/api/workspaces/{ws.id}")))["can_approve"] is True
