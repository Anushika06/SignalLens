"""History backfill from the web archive, the scheduler, and the demo lab."""

from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import func, select

from signallens.config import Settings
from signallens.db.base import utcnow
from signallens.db.models import (
    AgentRun,
    Claim,
    Event,
    Evidence,
    Fact,
    IntelligenceReport,
    Job,
    Notification,
    RunStep,
    Source,
    StateVersion,
    Workspace,
)
from signallens.db.session import transaction
from signallens.demo import PRICING_HTML, seed_demo_user, seed_lab_workspace, seed_sandbox
from signallens.jobs.worker import Worker
from signallens.llm.fake import ScriptedLLM
from signallens.runtime.gateway import ModelGateway
from signallens.runtime.services import build_services, sandbox_resolver
from signallens.search.fake import StaticSearch
from tests.conftest import TEST_DB
from tests.integration.fakes import PROMO_SENTENCE, Brain, FakeFetcher, FakeWayback

pytestmark = pytest.mark.db

URL = "https://nimbuspay.example/pricing"
PROMO = PRICING_HTML.replace("<h2>Enterprise</h2>", f"<p>{PROMO_SENTENCE}</p><h2>Enterprise</h2>")
CUT = PROMO.replace("at a flat 2% per", "at a flat 1.8% per")
CHALLENGE = ("<html><head><title>Just a moment...</title></head><body>Checking your browser before accessing. "
             "Enable JavaScript and cookies to continue.</body></html>")


def services_for(session_factory, brain: Brain, *, pages: dict[str, str], captures):
    settings = Settings(env="test", database_url=TEST_DB, secret_key="x" * 40, sandbox_enabled=True,
                        digest_hour_utc=0)
    llm = ModelGateway(ScriptedLLM(brain), provider_name="scripted", fast_model="scripted-fast",
                       reasoning_model="scripted-reasoning")
    return build_services(settings, session_factory, llm=llm, search=StaticSearch(lambda q, o: []),
                          fetcher=FakeFetcher(pages, sandbox_resolver=sandbox_resolver(session_factory)),
                          wayback=FakeWayback(captures))


async def test_backfill_reconstructs_history(session_factory):
    brain = Brain()
    brain.plan_sources = [{"ref": "pricing-page", "kind": "page", "url": URL, "entity_ref": "nimbus",
                           "areas": ["pricing"], "authority": "official", "priority": "high",
                           "check_every_hours": 12, "backfill": True, "reason": "Official pricing page"}]
    svc = services_for(session_factory, brain, pages={URL: CUT}, captures={URL: [
        ("20251015000000", PRICING_HTML),
        ("20251115000000", CHALLENGE),  # anti-bot page in the archive: must be skipped, not diffed
        ("20260115000000", PROMO),
        ("20260315000000", CUT),
    ]})
    async with transaction(session_factory) as s:
        org, user, _ = await seed_demo_user(s)
        ws = Workspace(org_id=org.id, name="Backfill", status="setup", profile={})
        s.add(ws)
        await s.flush()
        from signallens.agents.schemas import MonitoringPlanOut
        from signallens.db.models import MonitoringPolicy
        from signallens.pipeline.activation import activate_plan
        from signallens.pipeline.planning import normalize_plan

        plan = normalize_plan(MonitoringPlanOut.model_validate(brain.on_MonitoringPlanOut("", [], "")), ["Strategy"])
        policy = MonitoringPolicy(workspace_id=ws.id, version=1, status="pending_approval", request_text="Nimbus")
        s.add(policy)
        await s.flush()
        await activate_plan(s, policy=policy, plan=plan, user_id=user.id)
        wid = ws.id

    await Worker(svc, run_scheduler=False).run_until_idle()

    async with session_factory() as s:
        fact = (await s.execute(select(Fact).where(Fact.key == "pricing.standard_domestic_fee"))).scalar_one()
        versions = (await s.execute(select(StateVersion).where(StateVersion.fact_id == fact.id)
                                    .order_by(StateVersion.observed_at))).scalars().all()
        assert [v.observed_via for v in versions] == ["archive", "archive", "archive", "live"]
        assert [v.value_display[:4] for v in versions] == ["2% p", "2% p", "1.8%", "1.8%"]
        current = await s.get(StateVersion, fact.current_version_id)
        assert current.observed_via == "live"
        # the value last changed at the March capture, even though history arrived after the baseline
        assert fact.last_changed_at.date().isoformat() == "2026-03-15"

        events = (await s.execute(select(Event).where(Event.workspace_id == wid))).scalars().all()
        assert events and all(e.is_historical and e.status == "historical" for e in events)
        assert any("90 days" in e.title for e in events)
        cut = next(e for e in events if e.after_display and e.after_display.startswith("1.8%"))
        assert cut.details["between"][0].startswith("2026-01-15") and cut.details["between"][1].startswith("2026-03-15")
        ev = (await s.execute(select(Evidence).join(Claim, Claim.id == Evidence.claim_id)
                              .where(Claim.event_id == cut.id))).scalars().all()
        assert ev and all(e.is_archive and e.source_class == "primary" and e.quote_verified for e in ev)
        assert ev[0].url.startswith("https://web.archive.org/web/20260315")

        reports = (await s.execute(select(IntelligenceReport).where(IntelligenceReport.workspace_id == wid))).scalars().all()
        assert reports and all(r.is_historical for r in reports)
        assert (await s.execute(select(func.count(Notification.id)))).scalar_one() == 0  # history never alerts
        skipped = (await s.execute(select(RunStep.summary).where(RunStep.kind == "guardrail",
                                                                 RunStep.name == "quality_gate"))).scalars().all()
        assert any("2025-11-15" in x for x in skipped), skipped
        src = (await s.execute(select(Source).where(Source.workspace_id == wid))).scalar_one()
        assert src.config["backfilled"] is True and src.config["captures_skipped"] == 1
        assert brain.calls.get("ImpactOut", 0) == len(reports)
        backfill_run = (await s.execute(select(AgentRun).where(AgentRun.title.like("History backfill%")))).scalar_one()
        assert backfill_run.status == "succeeded"


async def test_scheduler_enqueues_due_checks_and_digest(session_factory):
    svc = services_for(session_factory, Brain(), pages={}, captures={})
    at = utcnow()
    async with transaction(session_factory) as s:
        org, user, _ = await seed_demo_user(s)
        ws = Workspace(org_id=org.id, name="Sched", status="monitoring", profile={})
        s.add(ws)
        await s.flush()
        due = Source(workspace_id=ws.id, kind="page", url="https://a.example/", baselined=True, active=True,
                     next_check_at=at - timedelta(minutes=1), check_every_minutes=60, current_interval_minutes=60)
        later = Source(workspace_id=ws.id, kind="page", url="https://b.example/", baselined=True, active=True,
                       next_check_at=at + timedelta(hours=1))
        unbaselined = Source(workspace_id=ws.id, kind="page", url="https://c.example/", baselined=False, active=True,
                             next_check_at=at - timedelta(hours=1))
        s.add_all([due, later, unbaselined])
    worker = Worker(svc, run_scheduler=False)
    assert await worker.tick(now=at) == 2  # the due check + a retry of the failed baseline
    assert await worker.tick(now=at) == 0  # pushed out; no duplicate check, no second digest
    async with session_factory() as s:
        kinds = sorted((await s.execute(select(Job.kind))).scalars())
    assert kinds == ["baseline_source", "check_source", "send_digest"]


async def test_demo_lab_seed_and_live_change(session_factory):
    brain = Brain()
    svc = services_for(session_factory, brain, pages={}, captures={})
    async with transaction(session_factory) as s:
        org, user, _ = await seed_demo_user(s)
        await seed_sandbox(s)
        ws = await seed_lab_workspace(s, org, user)
        assert await seed_lab_workspace(s, org, user) is None  # idempotent
        wid = ws.id
    worker = Worker(svc, run_scheduler=False)
    await worker.run_until_idle()
    async with transaction(session_factory) as s:
        from signallens.db.models import SandboxPage

        page = await s.get(SandboxPage, "nimbus-pay-pricing")
        page.html = page.html.replace("at a flat 2% per", "at a flat 1.8% per")
        src = (await s.execute(select(Source).where(Source.workspace_id == wid, Source.url.like("%pricing")))).scalar_one()
        src.next_check_at = utcnow() - timedelta(seconds=1)
    await worker.run_until_idle(schedule=True)
    async with session_factory() as s:
        reports = (await s.execute(select(IntelligenceReport).where(IntelligenceReport.workspace_id == wid))).scalars().all()
        assert len(reports) == 1 and reports[0].evidence_status == "confirmed"
        assert reports[0].previous_state.startswith("2%") and reports[0].current_state.startswith("1.8%")


async def test_values_missing_at_baseline_are_read_once_a_model_exists(session_factory):
    from signallens.jobs.queue import enqueue

    brain = Brain()
    no_model = services_for(session_factory, brain, pages={}, captures={})
    no_model.llm = None  # baseline taken before any model key was configured
    async with transaction(session_factory) as s:
        org, user, _ = await seed_demo_user(s)
        await seed_sandbox(s)
        wid = (await seed_lab_workspace(s, org, user)).id
    await Worker(no_model, run_scheduler=False).run_until_idle()

    async def fee_fact():
        async with session_factory() as s:
            return (await s.execute(select(Fact).where(Fact.workspace_id == wid,
                                                       Fact.key == "pricing.standard_domestic_fee"))).scalar_one()

    assert (await fee_fact()).current_version_id is None
    async with session_factory() as s:
        src = (await s.execute(select(Source).where(Source.workspace_id == wid, Source.url.like("%pricing")))).scalar_one()

    worker = Worker(services_for(session_factory, brain, pages={}, captures={}), run_scheduler=False)

    async def check():
        async with transaction(session_factory) as s:
            await enqueue(s, "check_source", {"source_id": str(src.id)}, workspace_id=wid, dedupe_key=f"check:{src.id}")
        await worker.run_until_idle()

    await check()  # page unchanged, model now available: missing values are read once
    assert (await fee_fact()).current_version_id is not None
    assert brain.calls.get("ExtractionOut") == 1
    await check()  # same page version: no second attempt
    assert brain.calls.get("ExtractionOut") == 1

    async with transaction(session_factory) as s:
        from signallens.db.models import SandboxPage

        page = await s.get(SandboxPage, "nimbus-pay-pricing")
        page.html = page.html.replace("at a flat 2% per", "at a flat 1.8% per")
    await check()
    async with session_factory() as s:
        reports = (await s.execute(select(IntelligenceReport).where(IntelligenceReport.workspace_id == wid))).scalars().all()
    assert len(reports) == 1 and reports[0].previous_state.startswith("2%") and reports[0].current_state.startswith("1.8%")
