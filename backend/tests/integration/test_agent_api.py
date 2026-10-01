"""Hosted agent endpoint (/api/agent/*): sync and async briefs, lenient bodies, auth, rate limits.

The web, archive, search and model are simulated (tests/brief_scenario.py); the API, job
queue, worker and database are real.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy import select

from signallens.api.app import create_app
from signallens.api.routes.agent import RateLimiter
from signallens.config import Settings
from signallens.db.models import AgentBrief, Job
from signallens.jobs.worker import Worker
from signallens.runtime.services import build_services
from tests.brief_scenario import BriefBrain, make_world
from tests.conftest import TEST_DB

pytestmark = pytest.mark.db


def _settings(**kw) -> Settings:
    base = dict(env="test", database_url=TEST_DB, secret_key="test-secret-key-for-signallens-tests-000",
                tavily_api_key=None, public_api_url="https://api.test", public_app_url="https://app.test",
                brief_timeout_s=60)
    return Settings(**{**base, **kw})


async def _env(session_factory, monkeypatch, **settings_kw):
    monkeypatch.setenv("SL_BRIEF_READER", "direct")  # never reach out to a real Tavily from tests
    world = make_world()
    svc = build_services(_settings(**settings_kw), session_factory, llm=world["llm"], search=world["search"],
                         fetcher=world["fetcher"], wayback=world["wayback"])
    app = create_app(svc.settings, services=svc)
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")
    return SimpleNamespace(svc=svc, client=client, brain=world["brain"], world=world)


@pytest.fixture
async def env(session_factory, monkeypatch):
    e = await _env(session_factory, monkeypatch)
    yield e
    await e.client.aclose()


async def test_health_and_manifest(env):
    health = (await env.client.get("/api/agent/health")).json()
    assert health["status"] == "ok" and health["llm_configured"] and health["search_configured"]
    manifest = (await env.client.get("/api/agent/manifest")).json()
    assert manifest["name"] == "signallens" and manifest["output"] == {"format": "markdown"}
    assert [i["name"] for i in manifest["inputs"]] == ["company", "your_company", "focus", "language", "months_back"]
    assert manifest["endpoints"]["brief"]["url"] == "https://api.test/api/agent/brief"
    assert manifest["auth"]["required"] is False


async def test_sync_brief_returns_markdown_and_stores_it(env):
    resp = await env.client.post("/api/agent/brief", json={"inputs": {"company": "Nimbus Pay",
                                                                      "your_company": "Orbit Payments"}})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["format"] == "markdown"
    assert body["response"].startswith("# Nimbus Pay — intelligence brief")
    assert "https://app.test" in body["response"]
    assert body["data"]["company"]["domain"] == "nimbuspay.in"
    assert body["trace"] and body["trace"][0]["name"] == "Search the web and news"
    async with env.svc.session_factory() as s:
        row = await s.get(AgentBrief, uuid.UUID(body["brief_id"]))
    assert row.status == "succeeded" and row.markdown == body["response"] and row.client.startswith("ip:")
    assert row.input["company"] == "Nimbus Pay" and row.finished_at is not None


@pytest.mark.parametrize("payload", [{"query": "Nimbus Pay"}, {"message": "Nimbus Pay"}, {"input": {"company": "Nimbus Pay"}}])
async def test_sync_brief_accepts_lenient_bodies(env, payload):
    resp = await env.client.post("/api/agent/brief", json=payload)
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["input"]["company"] == "Nimbus Pay"


async def test_plain_text_body_and_missing_company(env):
    resp = await env.client.post("/api/agent/brief", content=b"Nimbus Pay", headers={"content-type": "text/plain"})
    assert resp.status_code == 200
    bad = await env.client.post("/api/agent/brief", json={"focus": "Everything"})
    assert bad.status_code == 422 and "company" in bad.json()["detail"]


async def test_async_brief_is_queued_run_by_worker_and_pollable(env):
    resp = await env.client.post("/api/agent/briefs", json={"company": "Nimbus Pay", "language": "Hindi"})
    assert resp.status_code == 202
    queued = resp.json()
    assert queued["status"] == "queued" and queued["poll_url"].endswith(queued["brief_id"])
    poll = (await env.client.get(f"/api/agent/briefs/{queued['brief_id']}")).json()
    assert poll["status"] == "queued" and "response" not in poll
    async with env.svc.session_factory() as s:
        job = (await s.execute(select(Job).where(Job.kind == "agent_brief"))).scalar_one()
    assert job.max_attempts == 1
    assert await Worker(env.svc, run_scheduler=False).run_until_idle() == 1
    done = (await env.client.get(f"/api/agent/briefs/{queued['brief_id']}")).json()
    assert done["status"] == "succeeded" and done["format"] == "markdown"
    assert "क्या बदला" in done["response"]
    assert len(done["trace"]) >= 5
    assert (await env.client.get("/api/agent/briefs/00000000-0000-0000-0000-000000000000")).status_code == 404


async def test_failed_brief_is_reported(session_factory, monkeypatch):
    e = await _env(session_factory, monkeypatch)
    try:
        async def boom(*a, **kw):
            raise RuntimeError("provider exploded")

        monkeypatch.setattr("signallens.brief.service.run_brief", boom)
        resp = await e.client.post("/api/agent/brief", json={"company": "Nimbus Pay"})
        assert resp.status_code == 500 and "RuntimeError" in resp.json()["detail"]
        async with e.svc.session_factory() as s:
            row = (await s.execute(select(AgentBrief))).scalar_one()
        assert row.status == "failed" and "provider exploded" in row.error
    finally:
        await e.client.aclose()


async def test_api_key_required_when_configured(session_factory, monkeypatch):
    e = await _env(session_factory, monkeypatch, agent_api_keys="k-one, k-two")
    try:
        assert (await e.client.post("/api/agent/brief", json={"company": "Nimbus Pay"})).status_code == 401
        bad = await e.client.post("/api/agent/briefs", json={"company": "Nimbus Pay"}, headers={"X-API-Key": "nope"})
        assert bad.status_code == 401
        ok = await e.client.post("/api/agent/briefs", json={"company": "Nimbus Pay"}, headers={"X-API-Key": "k-two"})
        assert ok.status_code == 202
        bearer = await e.client.get(f"/api/agent/briefs/{ok.json()['brief_id']}",
                                    headers={"Authorization": "Bearer k-one"})
        assert bearer.status_code == 200
        assert (await e.client.get(f"/api/agent/briefs/{ok.json()['brief_id']}")).status_code == 401
        assert (await e.client.get("/api/agent/manifest")).json()["auth"]["required"] is True
    finally:
        await e.client.aclose()


async def test_rate_limit_per_client(session_factory, monkeypatch):
    e = await _env(session_factory, monkeypatch, agent_rate_limit_per_hour=2)
    try:
        for _ in range(2):
            assert (await e.client.post("/api/agent/briefs", json={"company": "Nimbus Pay"})).status_code == 202
        limited = await e.client.post("/api/agent/briefs", json={"company": "Nimbus Pay"})
        assert limited.status_code == 429 and int(limited.headers["retry-after"]) > 0
        other = await e.client.post("/api/agent/briefs", json={"company": "Nimbus Pay"},
                                    headers={"X-Forwarded-For": "203.0.113.9"})
        assert other.status_code == 202  # a different client has its own budget
    finally:
        await e.client.aclose()


async def test_not_configured_is_503(session_factory, monkeypatch):
    monkeypatch.setenv("SL_BRIEF_READER", "direct")
    svc = build_services(_settings(), session_factory, use_real_providers=False)
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(svc.settings, services=svc)),
                               base_url="http://test")
    try:
        assert (await client.get("/api/agent/health")).json()["llm_configured"] is False
        resp = await client.post("/api/agent/brief", json={"company": "Nimbus Pay"})
        assert resp.status_code == 503
    finally:
        await client.aclose()


def test_rate_limiter_window():
    rl = RateLimiter()
    assert rl.hit("a", 2, now=0) is None and rl.hit("a", 2, now=10) is None
    assert rl.hit("a", 2, now=20) == 3580
    assert rl.hit("a", 2, now=3601) is None  # the first hit has left the window


async def test_model_outage_still_returns_a_degraded_brief(session_factory, monkeypatch):
    """A model outage still yields a stored, successful (degraded) brief - never a 500."""
    monkeypatch.setenv("SL_BRIEF_READER", "direct")
    world = make_world(BriefBrain(fail={"*"}))
    svc = build_services(_settings(), session_factory, llm=world["llm"], search=world["search"],
                         fetcher=world["fetcher"], wayback=world["wayback"])
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(svc.settings, services=svc)),
                               base_url="http://test")
    try:
        resp = await client.post("/api/agent/brief", json={"company": "Nimbus Pay"})
        assert resp.status_code == 200
        assert "impact analysis could not be completed" in resp.json()["response"]
    finally:
        await client.aclose()
