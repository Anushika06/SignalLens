"""The whole product loop, through the real API, worker, database and pipeline.

Only the outside world is simulated: the web (FakeFetcher + demo-lab pages), the archive
(FakeWayback), search (StaticSearch) and the model (Brain, a scripted model).
"""

from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy import func, select

from signallens.api.app import create_app
from signallens.config import Settings
from signallens.db.models import (
    AgentRun,
    Evidence,
    IntelligenceReport,
    Notification,
    RunStep,
    SandboxPage,
    StateVersion,
)
from signallens.db.session import transaction
from signallens.demo import PRICING_HTML, seed_sandbox
from signallens.jobs.worker import Worker
from signallens.llm.fake import ScriptedLLM
from signallens.runtime.gateway import ModelGateway
from signallens.runtime.services import build_services, sandbox_resolver
from signallens.search.base import SearchResult
from signallens.search.fake import StaticSearch
from tests.conftest import TEST_DB
from tests.integration.fakes import (
    NEWS_A_QUOTE,
    NEWS_A_URL,
    NEWS_B_QUOTE,
    NEWS_B_URL,
    NEWS_C_QUOTE,
    NEWS_C_URL,
    NEWS_D_URL,
    PROMO_SENTENCE,
    Brain,
    FakeFetcher,
    FakeWayback,
    article,
)

pytestmark = pytest.mark.db


@pytest.fixture
async def env(session_factory):
    settings = Settings(env="test", database_url=TEST_DB, secret_key="test-secret-key-for-signallens-tests-000", sandbox_enabled=True)
    brain = Brain()
    llm = ModelGateway(ScriptedLLM(brain), provider_name="scripted", fast_model="scripted-fast",
                       reasoning_model="scripted-reasoning")
    results: dict[str, list[SearchResult]] = {"current": []}
    search = StaticSearch(lambda query, options: results["current"])
    fetcher = FakeFetcher(
        pages={
            NEWS_A_URL: article("Nimbus Pay partners with Zeta Bank", NEWS_A_QUOTE),
            NEWS_B_URL: article("Zeta Bank ties up with Nimbus Pay", NEWS_B_QUOTE),
            NEWS_C_URL: article("Fintech roundup", NEWS_C_QUOTE),
            NEWS_D_URL: article("Cricket scores", "India won the match by five wickets on Sunday evening in Pune."),
        },
        sandbox_resolver=sandbox_resolver(session_factory),
    )
    svc = build_services(settings, session_factory, llm=llm, search=search, fetcher=fetcher, wayback=FakeWayback({}))
    async with transaction(session_factory) as s:
        await seed_sandbox(s)
    app = create_app(settings, services=svc)
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")
    yield SimpleNamespace(svc=svc, brain=brain, client=client, results=results, sf=session_factory,
                          worker=Worker(svc, run_scheduler=False))
    await client.aclose()


async def ok(resp: httpx.Response, status: int = 200):
    assert resp.status_code == status, resp.text
    return resp.json() if resp.content else None


async def test_auth_is_required(env):
    assert (await env.client.get("/api/workspaces")).status_code == 401
    await ok(await env.client.post("/api/auth/signup", json={"email": "A@Example.com", "password": "password123",
                                                              "name": "Ana", "org_name": "Orbit"}))
    me = await ok(await env.client.get("/api/auth/me"))
    assert me["user"]["email"] == "a@example.com"
    await ok(await env.client.post("/api/auth/logout"), 204)
    env.client.cookies.clear()
    assert (await env.client.get("/api/auth/me")).status_code == 401
    assert (await env.client.post("/api/auth/login", json={"email": "a@example.com", "password": "nope"})).status_code == 401
    await ok(await env.client.post("/api/auth/login", json={"email": "a@example.com", "password": "password123"}))


async def test_full_loop(env):
    c = env.client
    await ok(await c.post("/api/auth/signup", json={"email": "ana@orbit.test", "password": "password123",
                                                     "name": "Ana", "org_name": "Orbit Payments"}))
    ws = await ok(await c.post("/api/workspaces", json={
        "name": "Payments landscape",
        "profile": {"company_name": "Orbit Payments", "description": "Payment gateway for Indian SMBs",
                    "products": ["Payment gateway"], "markets": ["India"], "competitors": ["Nimbus Pay"],
                    "relationship_to_subjects": "Nimbus Pay is a direct competitor"},
    }))
    wid = ws["id"]
    assert {t["name"] for t in ws["teams"]} >= {"Strategy", "Product", "Compliance"}

    # --- Phase 1: request → planner agent → plan awaiting approval -------------------------------------
    plan = await ok(await c.post(f"/api/workspaces/{wid}/plans", json={"request_text": "I want to monitor Nimbus Pay"}))
    assert plan["status"] == "planning"
    await env.worker.run_until_idle()
    plan = await ok(await c.get(f"/api/workspaces/{wid}/plans/{plan['id']}"))
    assert plan["status"] == "pending_approval", plan["error"]
    spec = plan["spec"]
    page_src = next(s for s in spec["sources"] if s["kind"] == "page")
    assert page_src["validation"]["ok"] is True and page_src["validation"]["title"]
    assert {a["key"] for a in spec["areas"]} == {"pricing", "partnerships"}
    run = await ok(await c.get(f"/api/workspaces/{wid}/runs/{plan['run_id']}"))
    assert run["status"] == "succeeded"
    assert [s["kind"] for s in run["steps"]][:2] == ["decision", "tool_call"]

    approved = await ok(await c.post(f"/api/workspaces/{wid}/plans/{plan['id']}/approve", json={}))
    assert approved["sources_created"] == 2 and approved["jobs_enqueued"] >= 2

    # --- Baseline: values extracted, no alerts ------------------------------------------------------------
    await env.worker.run_until_idle()
    detail = await ok(await c.get(f"/api/workspaces/{wid}"))
    assert detail["status"] == "monitoring"
    entities = await ok(await c.get(f"/api/workspaces/{wid}/entities"))
    nimbus = next(e for e in entities if e["name"] == "Nimbus Pay")
    assert any(e["role"] == "us" for e in entities)
    world = await ok(await c.get(f"/api/workspaces/{wid}/entities/{nimbus['id']}"))
    fee = next(f for f in world["facts"] if f["key"] == "pricing.standard_domestic_fee")
    assert fee["current"]["value_display"].startswith("2%") and fee["current"]["evidence_status"] == "confirmed"
    assert (await ok(await c.get(f"/api/workspaces/{wid}/reports"))) == []

    # --- The competitor changes its pricing page ---------------------------------------------------------
    new_html = PRICING_HTML.replace("at a flat 2% per", "at a flat 1.8% per").replace(
        "<h2>Enterprise</h2>", f"<p>{PROMO_SENTENCE}</p><h2>Enterprise</h2>").replace("&copy; 2026", "&copy; 2027")
    async with transaction(env.sf) as s:
        (await s.get(SandboxPage, "nimbus-pay-pricing")).html = new_html
    sources = await ok(await c.get(f"/api/workspaces/{wid}/sources"))
    page_source = next(s for s in sources if s["kind"] == "page")
    await ok(await c.post(f"/api/workspaces/{wid}/sources/{page_source['id']}/check"))
    await env.worker.run_until_idle()

    reports = await ok(await c.get(f"/api/workspaces/{wid}/reports"))
    assert len(reports) == 2, reports
    assert all(r["evidence_status"] == "confirmed" for r in reports)
    assert all(r["severity"] == "high" for r in reports)
    fee_report = next(r for r in reports if r["previous_state"] and r["previous_state"].startswith("2%"))
    assert fee_report["current_state"].startswith("1.8%")

    card = await ok(await c.get(f"/api/workspaces/{wid}/reports/{fee_report['id']}"))
    assert card["fact"] and [v["value_display"][:4] for v in card["fact"]["history"]] == ["2% p", "1.8%"]
    assert card["fact"]["history"][-1]["valid_from"].startswith("2026-09-27")  # effective date found by the investigator
    assert card["evidence"] and all(e["quote_verified"] for e in card["evidence"])
    assert card["evidence"][0]["source_class"] == "primary"
    assert {t["name"] for t in card["affected_teams"]} >= {"Strategy", "Product"}  # unknown team names dropped
    assert card["investigation"] and card["investigation"]["steps"] >= 2
    assert card["why_it_matters"] and card["assumptions"]

    async with env.sf() as s:
        notes = (await s.execute(select(func.count(Notification.id)).where(Notification.channel == "inbox",
                                                                           Notification.status == "sent"))).scalar_one()
        assert notes >= 2  # high severity in a critical area → immediate
        versions = (await s.execute(select(func.count(StateVersion.id)))).scalar_one()
        assert versions >= 3  # 2% and 3.5% at baseline, then 1.8%

    overview = await ok(await c.get(f"/api/workspaces/{wid}/overview"))
    f = overview["funnel"]
    assert f["checks"] >= 1 and f["published"] == 2 and f["material"] >= 2 and f["filtered"] >= 1
    assert overview["subjects"][0]["name"] == "Nimbus Pay"
    assert overview["activity"], "activity feed should not be empty"
    filtered = await ok(await c.get(f"/api/workspaces/{wid}/filtered"))
    assert any(x["tier"] == 2 for x in filtered)

    # --- Feedback → learned rule → undo -----------------------------------------------------------------
    promo = next(r for r in reports if r["id"] != fee_report["id"])
    first = await ok(await c.post(f"/api/workspaces/{wid}/reports/{fee_report['id']}/feedback",
                                  json={"verdict": "not_relevant", "reason": "too_minor"}))
    assert first["learned_rules"] == [] and "One more" in first["message"]
    second = await ok(await c.post(f"/api/workspaces/{wid}/reports/{promo['id']}/feedback",
                                   json={"verdict": "not_relevant", "reason": "too_minor"}))
    assert second["learned_rules"] and second["learned_rules"][0]["effect"] == {"threshold": "medium"}
    rules = await ok(await c.get(f"/api/workspaces/{wid}/learned-rules"))
    assert len(rules) == 1 and rules[0]["active"]
    policy = await ok(await c.get(f"/api/workspaces/{wid}/policy"))
    assert next(a for a in policy["areas"] if a["key"] == "pricing")["importance"] == "critical"
    revoked = await ok(await c.delete(f"/api/workspaces/{wid}/learned-rules/{rules[0]['id']}"))
    assert revoked["active"] is False

    # --- Human approval for an external share --------------------------------------------------------------
    approval = await ok(await c.post(f"/api/workspaces/{wid}/reports/{fee_report['id']}/share",
                                     json={"recipient": "advisor@partner.test", "note": "FYI"}))  # the UI sends "recipient"
    assert approval["status"] == "pending" and approval["can_decide"] is True  # the sole owner may self-approve
    decided = await ok(await c.post(f"/api/workspaces/{wid}/approvals/{approval['id']}/decide",
                                    json={"decision": "approve", "note": "OK to share"}))
    assert decided["status"] == "approved"
    await env.worker.run_until_idle()
    done = (await ok(await c.get(f"/api/workspaces/{wid}/approvals")))[0]
    assert done["status"] == "executed" and done["result"]["delivered"] is False  # no SMTP configured: nothing sent
    assert done["payload"]["to"] == "advisor@partner.test" and done["decision_note"] == "OK to share (self-approved: sole approver)"

    # --- A news event reported by several outlets: one event, corroborated ------------------------------------
    env.brain.triage_items = {
        "news-a": {"entity": "Nimbus Pay", "event_type": "partnership", "area": "partnerships",
                   "headline": "Nimbus Pay partners with Zeta Bank", "claim": "Nimbus Pay partnered with Zeta Bank.",
                   "counterparty": "Zeta Bank", "materiality": "high", "reason": "Distribution partnership"},
        "news-b": {"entity": "Nimbus Pay", "event_type": "partnership", "area": "partnerships",
                   "headline": "Zeta Bank ties up with Nimbus Pay", "claim": "Zeta Bank partnered with Nimbus Pay.",
                   "counterparty": "Zeta Bank Ltd", "materiality": "high", "reason": "Distribution partnership"},
    }
    env.results["current"] = [
        SearchResult(url=NEWS_A_URL, title="Nimbus Pay partners with Zeta Bank", snippet=NEWS_A_QUOTE),
        SearchResult(url=NEWS_B_URL, title="Zeta Bank ties up with Nimbus Pay", snippet=NEWS_B_QUOTE),
        SearchResult(url=NEWS_D_URL, title="Cricket scores", snippet="India won the match."),
    ]
    news_source = next(s for s in sources if s["kind"] == "news")
    await ok(await c.post(f"/api/workspaces/{wid}/sources/{news_source['id']}/check"))
    await env.worker.run_until_idle()
    reports = await ok(await c.get(f"/api/workspaces/{wid}/reports"))
    partnership = [r for r in reports if r["event_type"] == "partnership"]
    assert len(partnership) == 1, [r["title"] for r in reports]
    card = await ok(await c.get(f"/api/workspaces/{wid}/reports/{partnership[0]['id']}"))
    publishers = {e["publisher"] for e in card["evidence"]}
    assert len(publishers) == 3, card["evidence"]  # two from clustering, one found by the investigator
    assert card["evidence_status"] == "corroborated"
    world = await ok(await c.get(f"/api/workspaces/{wid}/entities/{nimbus['id']}"))
    assert any(r["predicate"] == "partners_with" and r["other"]["name"].startswith("Zeta") for r in world["relationships"])

    # Re-running the same search finds nothing new (seen items are remembered).
    await ok(await c.post(f"/api/workspaces/{wid}/sources/{news_source['id']}/check"))
    await env.worker.run_until_idle()
    checks = await ok(await c.get(f"/api/workspaces/{wid}/sources/{news_source['id']}/checks"))
    assert checks[0]["outcome"] == "no_new_items"

    async with env.sf() as s:
        runs = (await s.execute(select(AgentRun.agent, AgentRun.status))).all()
        assert ("investigator", "succeeded") in runs and ("impact_analyst", "succeeded") in runs
        guard = (await s.execute(select(func.count(RunStep.id)).where(RunStep.kind == "error"))).scalar_one()
        assert guard == 0
        agent_evidence = (await s.execute(select(func.count(Evidence.id)).where(Evidence.added_by == "agent"))).scalar_one()
        assert agent_evidence >= 1
        assert (await s.execute(select(func.count(IntelligenceReport.id)))).scalar_one() == 3
