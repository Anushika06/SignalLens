"""Ask: the question → agent → cited answer loop, through the real API, worker and database.

The model is scripted; the memory it searches is seeded directly. A second organisation's
workspace holds look-alike rows (same entity name) that must never reach the agent.
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import httpx
import pytest

from signallens.api.app import create_app
from signallens.config import Settings
from signallens.db.base import utcnow
from signallens.db.models import (
    Claim,
    Entity,
    Event,
    Evidence,
    Fact,
    IntelligenceReport,
    Organization,
    StateVersion,
    Team,
    Workspace,
)
from signallens.db.session import transaction
from signallens.jobs.worker import Worker
from signallens.llm.fake import ScriptedLLM
from signallens.runtime.core import Budget, RunContext
from signallens.runtime.gateway import ModelGateway
from signallens.runtime.services import build_services
from signallens.tools.memory import (
    GetCardTool,
    GetFactHistoryTool,
    RecentChangesArgs,
    RecentChangesTool,
    SearchMemoryTool,
)
from tests.conftest import TEST_DB
from tests.integration.fakes import FakeFetcher, FakeWayback

pytestmark = pytest.mark.db

FACT_RE = re.compile(r"\[fact:([0-9a-f-]{36})\]")
CARD_RE = re.compile(r"\[card:([0-9a-f-]{36})\]")


def _d(y: int, m: int, d: int) -> datetime:
    return datetime(y, m, d, 9, 0, tzinfo=UTC)


async def seed_memory(s, ws_id: uuid.UUID, *, tag: str, fee_old: str, fee_new: str, compliance_team: uuid.UUID | None = None):
    """An entity with a versioned fee fact, a pricing card with evidence, and a regulation card."""
    ent = Entity(id=uuid.uuid4(), workspace_id=ws_id, kind="company", role="competitor", name="Nimbus Pay",
                 name_key="nimbus pay", aliases=["Nimbus"], official_domains=["nimbuspay.example"],
                 description=f"Payment gateway {tag}")
    s.add(ent)
    await s.flush()
    fact = Fact(id=uuid.uuid4(), workspace_id=ws_id, entity_id=ent.id, area="pricing",
                key="pricing.standard_domestic_fee", label="Standard domestic fee", value_type="percent")
    s.add(fact)
    await s.flush()
    event = Event(id=uuid.uuid4(), workspace_id=ws_id, entity_id=ent.id, fact_id=fact.id, area="pricing",
                  event_type="pricing", title=f"Nimbus Pay cuts standard fee to {fee_new} {tag}",
                  summary="Standard plan fee lowered.", status="published", evidence_status="confirmed",
                  materiality="high", detected_at=utcnow() - timedelta(days=5), occurred_at=utcnow() - timedelta(days=6))
    s.add(event)
    await s.flush()
    v1 = StateVersion(id=uuid.uuid4(), fact_id=fact.id, value_display=fee_old, value_key=f"{tag}-old",
                      observed_at=_d(2026, 1, 5), observed_via="archive", evidence_status="confirmed",
                      quote=f"flat {fee_old} per successful transaction")
    v2 = StateVersion(id=uuid.uuid4(), fact_id=fact.id, value_display=fee_new, value_key=f"{tag}-new",
                      observed_at=utcnow() - timedelta(days=5), observed_via="live", evidence_status="confirmed",
                      quote=f"flat {fee_new} per successful transaction", event_id=event.id)
    s.add_all([v1, v2])
    await s.flush()
    fact.current_version_id, fact.first_seen_at, fact.last_changed_at = v2.id, v1.observed_at, v2.observed_at
    claim = Claim(id=uuid.uuid4(), workspace_id=ws_id, event_id=event.id, entity_id=ent.id,
                  statement=f"Nimbus Pay lowered its standard fee to {fee_new}", evidence_status="confirmed")
    s.add(claim)
    await s.flush()
    s.add(Evidence(workspace_id=ws_id, claim_id=claim.id, url="https://nimbuspay.example/pricing", publisher="nimbuspay.example",
                   source_class="primary", stance="supports", quote=f"flat {fee_new} per successful transaction",
                   quote_verified=True))
    card = IntelligenceReport(id=uuid.uuid4(), workspace_id=ws_id, event_id=event.id, entity_id=ent.id, area="pricing",
                              title=f"Nimbus Pay cuts its standard fee to {fee_new} {tag}", change_label="Pricing change",
                              what_changed=f"The standard domestic fee fell from {fee_old} to {fee_new}.",
                              why_it_matters="Puts pressure on our SMB pricing.", severity="high",
                              evidence_status="confirmed", previous_state=fee_old, current_state=fee_new,
                              detected_at=event.detected_at, occurred_at=event.occurred_at)
    reg_event = Event(id=uuid.uuid4(), workspace_id=ws_id, entity_id=ent.id, area="regulation", event_type="regulatory",
                      title=f"RBI penalty notice {tag}", status="published", evidence_status="single_source",
                      detected_at=utcnow() - timedelta(days=2))
    s.add_all([card, reg_event])
    await s.flush()
    reg_card = IntelligenceReport(id=uuid.uuid4(), workspace_id=ws_id, event_id=reg_event.id, entity_id=ent.id,
                                  area="regulation", title=f"Regulator fines Nimbus Pay {tag}", change_label="Regulatory action",
                                  what_changed="A penalty was imposed.", why_it_matters="Compliance exposure.",
                                  severity="medium", evidence_status="single_source", detected_at=reg_event.detected_at,
                                  affected_team_ids=[str(compliance_team)] if compliance_team else [])
    # Noise that must never be offered to the agent.
    s.add_all([reg_card, Event(workspace_id=ws_id, entity_id=ent.id, title=f"Footer tweak pricing {tag}",
                               status="filtered", area="pricing")])
    return SimpleNamespace(entity=ent, fact=fact, card=card, reg_card=reg_card, event=event)


class AskScript:
    """Scripted Ask agent: search → fact history → finish (with bad citations, then again)."""

    def __init__(self, other_card: uuid.UUID):
        self.other_card = other_card
        self.calls: list[str] = []
        self.loop_forever = False

    def __call__(self, system, messages, json_schema, name):
        self.calls.append("\n".join(m.content for m in messages))
        obs = [m.content for m in messages if m.role == "user" and m.content.startswith("OBSERVATION")]
        guardrails = sum(1 for m in messages if m.role == "user" and m.content.startswith("GUARDRAIL"))
        if name == "AskFinish":  # out of steps: write the answer from the research so far
            fact = FACT_RE.search(messages[-1].content)
            return {"answer_markdown": "Nimbus Pay's standard fee is 1.8% [1].",
                    "citations": [{"kind": "fact", "id": fact.group(1), "label": "fee"}],
                    "evidence_note": "Confirmed on the official page.", "follow_up_questions": []}
        assert name == "Decision", name
        if self.loop_forever:
            return {"thought": "Search again.", "action": "search_memory", "args": {"query": f"Nimbus fee {len(obs)}"}}
        if not obs:
            return {"thought": "Search memory.", "action": "search_memory", "args": {"query": "Nimbus Pay pricing fee"}}
        if len(obs) == 1:
            fact = FACT_RE.search(obs[0]).group(1)
            return {"thought": "Read the fee history.", "action": "get_fact_history", "args": {"fact_id": fact}}
        fact = FACT_RE.search(obs[0]).group(1)
        card = CARD_RE.search(obs[0]).group(1)
        return {"thought": "Answer." if guardrails == 0 else "Answer again.", "action": "finish", "args": {
            "answer_markdown": ("Nimbus Pay cut its standard domestic fee from 2% to 1.8% [1][2]. "
                                "Something else [3]. Junk [4]."),
            "citations": [
                {"kind": "fact", "id": f"fact:{fact}", "label": "model label"},
                {"kind": "card", "id": card.upper(), "label": "card"},
                {"kind": "card", "id": str(self.other_card), "label": "other workspace"},
                {"kind": "entity", "id": "not-a-uuid", "label": "junk"},
            ],
            "evidence_note": "The fee change is confirmed by the official pricing page.",
            "follow_up_questions": ["When did it take effect?", "How does it compare?", "Who else cut fees?", "Fourth?"],
        }}


@pytest.fixture
async def env(session_factory):
    settings = Settings(env="test", database_url=TEST_DB, secret_key="test-secret-key-for-signallens-tests-000",
                        sandbox_enabled=False)
    script = AskScript(other_card=uuid.uuid4())
    llm = ModelGateway(ScriptedLLM(script), provider_name="scripted", fast_model="scripted-fast",
                       reasoning_model="scripted-reasoning")
    svc = build_services(settings, session_factory, llm=llm, search=None, fetcher=FakeFetcher({}),
                         wayback=FakeWayback({}), use_real_providers=False)
    app = create_app(settings, services=svc)
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")
    r = await client.post("/api/auth/signup", json={"email": "ana@orbit.test", "password": "password123",
                                                     "name": "Ana", "org_name": "Orbit Payments"})
    assert r.status_code == 200, r.text
    r = await client.post("/api/workspaces", json={"name": "Payments", "profile": {
        "company_name": "Orbit Payments", "description": "Payment gateway for Indian SMBs"}})
    assert r.status_code == 200, r.text
    wid = uuid.UUID(r.json()["id"])
    async with transaction(session_factory) as s:
        compliance = next(t for t in (await s.execute(Team.__table__.select().where(Team.workspace_id == wid))).all()
                          if t.name == "Compliance")
        mine = await seed_memory(s, wid, tag="", fee_old="2%", fee_new="1.8%", compliance_team=compliance.id)
        org_b = Organization(id=uuid.uuid4(), name="Rival Corp")
        s.add(org_b)
        await s.flush()
        ws_b = Workspace(id=uuid.uuid4(), org_id=org_b.id, name="Rival workspace")
        s.add(ws_b)
        await s.flush()
        theirs = await seed_memory(s, ws_b.id, tag="SECRETB", fee_old="9.1%", fee_new="9.9%")
    script.other_card = theirs.card.id
    yield SimpleNamespace(svc=svc, client=client, wid=wid, ws_b=ws_b.id, mine=mine, theirs=theirs, script=script,
                          worker=Worker(svc, run_scheduler=False), sf=session_factory)
    await client.aclose()


def _ctx(env, workspace_id: uuid.UUID) -> RunContext:
    return RunContext(env.svc, run_id=uuid.uuid4(), workspace_id=workspace_id, agent="ask", budget=Budget())


async def test_memory_tools_are_workspace_scoped(env):
    ctx = _ctx(env, env.wid)
    obs = await SearchMemoryTool().run(ctx, SearchMemoryTool.Args(query="Nimbus Pay pricing fee"))
    assert obs.ok and obs.untrusted
    assert str(env.mine.fact.id) in obs.content and str(env.mine.card.id) in obs.content
    assert "SECRETB" not in obs.content and str(env.theirs.fact.id) not in obs.content
    assert "Footer tweak" not in obs.content  # filtered noise is not memory
    assert "2026-01-05: 2%" in obs.content  # value history with dates
    assert ("fact", str(env.mine.fact.id)) in ctx.scratch["seen"]

    other = _ctx(env, env.ws_b)
    obs_b = await SearchMemoryTool().run(other, SearchMemoryTool.Args(query="Nimbus Pay pricing fee"))
    assert str(env.theirs.fact.id) in obs_b.content and str(env.mine.fact.id) not in obs_b.content

    # A past value is searchable; ILIKE fallback finds domain-ish tokens FTS does not stem.
    obs = await SearchMemoryTool().run(ctx, SearchMemoryTool.Args(query="nimbuspay.example"))
    assert str(env.mine.entity.id) in obs.content and "SECRETB" not in obs.content
    obs = await SearchMemoryTool().run(ctx, SearchMemoryTool.Args(query="zzz-unknown-thing"))
    assert obs.ok and "No matches" in obs.content

    # Ids from another workspace are refused.
    assert not (await GetFactHistoryTool().run(ctx, GetFactHistoryTool.Args(fact_id=str(env.theirs.fact.id)))).ok
    assert not (await GetCardTool().run(ctx, GetCardTool.Args(report_id=str(env.theirs.card.id)))).ok
    assert not (await GetCardTool().run(ctx, GetCardTool.Args(report_id="nope"))).ok
    card = await GetCardTool().run(ctx, GetCardTool.Args(report_id=str(env.mine.card.id)))
    assert card.ok and "assessment, not fact" in card.content and "flat 1.8% per successful transaction" in card.content

    week = await RecentChangesTool().run(ctx, RecentChangesArgs(days=7))
    assert str(env.mine.card.id) in week.content and str(env.mine.reg_card.id) in week.content
    assert "SECRETB" not in week.content
    assert "Footer tweak" not in week.content  # filtered noise is not a change
    compliance = await RecentChangesTool().run(ctx, RecentChangesArgs(days=7, team="Compliance"))
    assert str(env.mine.reg_card.id) in compliance.content and str(env.mine.card.id) not in compliance.content
    bad_team = await RecentChangesTool().run(ctx, RecentChangesArgs(days=7, team="Astronauts"))
    assert not bad_team.ok and "Compliance" in bad_team.content


async def test_ask_answers_with_validated_citations(env):
    c, wid = env.client, env.wid
    r = await c.post(f"/api/workspaces/{wid}/ask", json={"question": "What has Nimbus Pay changed in pricing?"})
    assert r.status_code == 202, r.text
    run_id = r.json()["run_id"]
    assert r.json()["status"] == "queued"
    queued = (await c.get(f"/api/workspaces/{wid}/ask/{run_id}")).json()
    assert queued["status"] == "queued" and queued["answer_markdown"] is None

    await env.worker.run_until_idle()

    d = (await c.get(f"/api/workspaces/{wid}/ask/{run_id}")).json()
    assert d["status"] == "succeeded", d["error"]
    assert d["question"] == "What has Nimbus Pay changed in pricing?" and d["asked_by"] == "Ana"
    # Invalid citations (another workspace's card, a junk id) were refused once by the guardrail,
    # then dropped on validation; markers are renumbered and labels come from the database.
    assert [(x["kind"], x["id"]) for x in d["citations"]] == [("fact", str(env.mine.fact.id)), ("card", str(env.mine.card.id))]
    assert d["citations"][0]["label"] == "Nimbus Pay · Standard domestic fee"
    assert d["citations"][0]["entity_id"] == str(env.mine.entity.id)
    assert d["answer_markdown"] == ("Nimbus Pay cut its standard domestic fee from 2% to 1.8% [1][2]. "
                                    "Something else. Junk.")
    assert len(d["follow_up_questions"]) == 3 and d["evidence_note"]
    kinds = [st["kind"] for st in d["steps"]]
    assert kinds[:4] == ["decision", "tool_call", "decision", "tool_call"]
    assert kinds.count("guardrail") == 2  # unseen-citation objection + dropped-citation note
    search_step = next(st for st in d["steps"] if st["name"] == "search_memory" and st["kind"] == "tool_call")
    assert search_step["output"]["facts"] == [str(env.mine.fact.id)]
    assert d["usage"]["llm_calls"] == 4 and d["usage"]["tool_calls"] == 2
    # Nothing from the other organisation ever reached the model.
    assert not any("SECRETB" in call for call in env.script.calls)
    assert all("<untrusted_content" in call for call in env.script.calls[1:])

    history = (await c.get(f"/api/workspaces/{wid}/ask")).json()
    assert [h["id"] for h in history] == [run_id] and history[0]["citations"] and history[0]["steps_count"] == len(d["steps"])
    runs = (await c.get(f"/api/workspaces/{wid}/runs?agent=ask")).json()
    assert [x["id"] for x in runs] == [run_id]
    assert (await c.get(f"/api/workspaces/{wid}/ask/{uuid.uuid4()}")).status_code == 404


async def test_ask_out_of_steps_writes_answer_from_research(env):
    env.script.loop_forever = True
    r = await env.client.post(f"/api/workspaces/{env.wid}/ask", json={"question": "Nimbus fee?"})
    await env.worker.run_until_idle()
    d = (await env.client.get(f"/api/workspaces/{env.wid}/ask/{r.json()['run_id']}")).json()
    assert d["status"] == "succeeded", d["error"]
    assert d["citations"][0]["id"] == str(env.mine.fact.id)
    assert any(st["kind"] == "guardrail" and st["name"] == "budget" for st in d["steps"])
    assert sum(1 for st in d["steps"] if st["kind"] == "decision") == 6


async def test_ask_validation_and_limits(env):
    c, wid = env.client, env.wid
    assert (await c.post(f"/api/workspaces/{wid}/ask", json={"question": "  "})).status_code == 422
    for _ in range(3):
        assert (await c.post(f"/api/workspaces/{wid}/ask", json={"question": "Anything new?"})).status_code == 202
    assert (await c.post(f"/api/workspaces/{wid}/ask", json={"question": "Anything new?"})).status_code == 429
    assert (await c.get(f"/api/workspaces/{env.ws_b}/ask")).status_code == 404
