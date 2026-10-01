"""Evidence arriving after publication: upgrades are silent, a downgrade to conflicting re-notifies."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import func, select

from signallens.db.models import Claim, Event, IntelligenceReport, Notification, Organization, Team, Workspace
from signallens.db.session import transaction
from signallens.store.evidence import add_evidence, refresh_status

pytestmark = pytest.mark.db


async def _published_card(s):
    org = Organization(id=uuid.uuid4(), name="Org")
    ws = Workspace(id=uuid.uuid4(), org_id=org.id, name="W", status="monitoring", profile={})
    team = Team(id=uuid.uuid4(), workspace_id=ws.id, name="Strategy", areas=[])
    event = Event(id=uuid.uuid4(), workspace_id=ws.id, title="Nimbus Pay partners with Zeta Bank", status="published",
                  area="partnerships", event_type="partnership")
    claim = Claim(id=uuid.uuid4(), workspace_id=ws.id, event_id=event.id, statement="Nimbus Pay partnered with Zeta Bank.")
    report = IntelligenceReport(
        id=uuid.uuid4(), workspace_id=ws.id, event_id=event.id, area="partnerships", title=event.title,
        change_label="New partnership", what_changed="...", why_it_matters="...", severity="high",
        evidence_status="unverified", affected_team_ids=[str(team.id)],
    )
    for row in (org, ws, team, event, claim, report):  # no ORM relationships: flush in FK order
        s.add(row)
        await s.flush()
    return ws, event, claim, report


async def _notes(s) -> int:
    return (await s.execute(select(func.count(Notification.id)))).scalar_one()


async def test_upgrade_is_silent_and_conflict_renotifies(session_factory):
    async with transaction(session_factory) as s:
        ws, event, claim, report = await _published_card(s)

        async def add(url, publisher, cls, stance, quote):
            await add_evidence(s, workspace_id=ws.id, claim_id=claim.id, url=url, quote=quote, stance=stance,
                               source_class=cls, publisher=publisher, quote_verified=True)
            return await refresh_status(s, claim_id=claim.id, event_id=event.id, distrusted=set())

        a = await add("https://a.example/1", "a.example", "independent", "supports", "Nimbus Pay partnered with Zeta Bank.")
        assert a.status == "single_source" and await _notes(s) == 0
        a = await add("https://b.example/2", "b.example", "independent", "supports", "Zeta Bank is now a Nimbus Pay partner.")
        assert a.status == "corroborated" and await _notes(s) == 0  # upgrade: silent
        a = await add("https://zetabank.example/x", "zetabank.example", "primary", "contradicts",
                      "Zeta Bank has no agreement with Nimbus Pay.")
        assert a.status == "conflicting"
        assert await _notes(s) == 1  # downgrade to conflicting: the card's team is told again
        a = await add("https://c.example/3", "c.example", "independent", "supports", "Reports say they partnered.")
        assert a.status == "conflicting" and await _notes(s) == 1  # already conflicting: no repeat
        refreshed = await s.get(IntelligenceReport, report.id)
        assert refreshed.evidence_status == "conflicting" and "Conflicting" in refreshed.evidence_summary
