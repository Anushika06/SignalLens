"""Read-only tools over a workspace's memory: facts and their history, events, cards, entities.

Used by the Ask agent. Every query is scoped to ``ctx.workspace_id``; nothing here writes.
Results carry the ids the agent must cite, and every id an agent sees is remembered in
``ctx.scratch["seen"]`` so the finish guardrail can tell a real citation from an invented one.

Search is PostgreSQL full-text search (``to_tsvector('english', …) @@ websearch_to_tsquery``)
with an ``ILIKE`` fallback for names and codes the English parser does not stem well.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timedelta
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import Text, cast, func, literal_column, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from signallens.db.base import utcnow
from signallens.db.models import (
    Claim,
    Entity,
    Event,
    Evidence,
    Fact,
    IntelligenceReport,
    StateVersion,
    Team,
)
from signallens.runtime.core import Observation, RunContext, Tool
from signallens.search.base import SearchError

# ---------------------------------------------------------------------------------------
# Query building (pure functions; unit-tested)
# ---------------------------------------------------------------------------------------

# Question filler that would otherwise dominate an OR query ("what", "this", "week"…).
STOPWORDS = frozenset("""
a about above after again against all also am an and any are as at be been before being below between both but by
can could did do does doing done during each few for from further had has have having he her here hers him his how
i if in into is it its itself just let me more most my no nor not now of off on once only or other our ours out over
own same she should so some such than that the their theirs them then there these they this those through to too
under until up very was we were what when where which while who whom why will with would you your yours
anything something everything tell show give list find know see look looking please us any much many recent
recently lately latest new news currently current today yesterday week weeks month months year years ago since
ever still yet happened happen happening changed change changes thing things
""".split())

_WORD_RE = re.compile(r"[^\W_][\w&.'+-]*", re.UNICODE)
_PHRASE_RE = re.compile(r'"([^"]{2,80})"')
MAX_TERMS = 12


def search_terms(query: str) -> list[str]:
    """Significant lower-case words of a question, in order, without duplicates or filler."""
    out: list[str] = []
    for raw in _WORD_RE.findall(query.lower()):
        word = raw.strip(".'+-&")
        if word.endswith("'s"):
            word = word[:-2]
        if len(word) < 2 or word in STOPWORDS or word in out:
            continue
        out.append(word)
        if len(out) >= MAX_TERMS:
            break
    return out


def build_tsquery(query: str) -> str | None:
    """A ``websearch_to_tsquery`` string that ORs the significant terms (and keeps "quoted phrases").

    A natural question ANDed term by term almost never matches anything, so terms are ORed and
    ``ts_rank`` puts rows that match more of them first. ``websearch_to_tsquery`` never raises on
    odd input, and terms never start with ``-`` (which it would read as NOT).
    """
    phrases = [" ".join(search_terms(p)) for p in _PHRASE_RE.findall(query)]
    phrases = [p for p in phrases if p]
    rest = _PHRASE_RE.sub(" ", query)
    parts = [f'"{p}"' for p in phrases]
    parts += [t for t in search_terms(rest) if t not in phrases]
    return " or ".join(parts[:MAX_TERMS]) or None


def like_patterns(query: str) -> list[str]:
    """``ILIKE`` patterns for the fallback search, with LIKE wildcards in the terms escaped."""
    terms = search_terms(query) or ([query.strip().lower()] if query.strip() else [])
    return [f"%{t.replace(chr(92), chr(92) * 2).replace('%', r'\%').replace('_', r'\_')}%" for t in terms[:6]]


def _doc(*cols: Any) -> ColumnElement:
    return func.concat_ws(" ", *cols)


def fts_match(tsquery: str, *cols: Any) -> tuple[ColumnElement, ColumnElement]:
    """(where clause, rank) for full-text matching ``tsquery`` against the concatenated columns."""
    english = literal_column("'english'::regconfig")
    vector = func.to_tsvector(english, _doc(*cols))
    q = func.websearch_to_tsquery(english, tsquery)
    return vector.op("@@")(q), func.ts_rank(vector, q)


def like_match(patterns: list[str], *cols: Any) -> ColumnElement:
    doc = _doc(*cols)
    return or_(*[doc.ilike(p) for p in patterns])


def _uuid(value: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(value).strip())
    except (ValueError, AttributeError):
        return None


def _d(value: datetime | None) -> str:
    return value.date().isoformat() if value else "date unknown"


def _clip(text: str | None, n: int) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= n else text[: n - 1] + "…"


def _seen(ctx: RunContext, kind: str, *ids: Any) -> None:
    seen: set[tuple[str, str]] = ctx.scratch.setdefault("seen", set())
    for i in ids:
        if i:
            seen.add((kind, str(i)))


# ---------------------------------------------------------------------------------------
# Searches (each returns rows for one workspace only)
# ---------------------------------------------------------------------------------------


async def _ranked(s: AsyncSession, stmt, cols: tuple, tsquery: str | None, patterns: list[str], order_fallback,
                  limit: int) -> list:
    """Run ``stmt`` with full-text matching; fall back to ILIKE when FTS finds nothing."""
    rows: list = []
    if tsquery:
        where, rank = fts_match(tsquery, *cols)
        rows = list((await s.execute(stmt.where(where).order_by(rank.desc(), order_fallback).limit(limit))).all())
    if not rows and patterns:
        rows = list((await s.execute(stmt.where(like_match(patterns, *cols)).order_by(order_fallback).limit(limit))).all())
    return rows


async def search_facts(s: AsyncSession, workspace_id: uuid.UUID, query: str, *, limit: int = 8) -> list[tuple[Fact, Entity]]:
    tsq, pats = build_tsquery(query), like_patterns(query)
    current = StateVersion
    stmt = (select(Fact, Entity).join(Entity, Entity.id == Fact.entity_id)
            .outerjoin(current, current.id == Fact.current_version_id)
            .where(Fact.workspace_id == workspace_id, Fact.active.is_(True)))
    cols = (Entity.name, cast(Entity.aliases, Text), Fact.label, func.translate(Fact.key, "._", "  "), Fact.area,
            current.value_display)
    rows = await _ranked(s, stmt, cols, tsq, pats, Fact.last_changed_at.desc().nulls_last(), limit)
    found = {f.id for f, _ in rows}
    if len(rows) < limit:
        # Values the fact once had (e.g. "1.9%") are searchable too.
        vstmt = (select(Fact, Entity).join(StateVersion, StateVersion.fact_id == Fact.id)
                 .join(Entity, Entity.id == Fact.entity_id)
                 .where(Fact.workspace_id == workspace_id, Fact.active.is_(True)))
        if found:
            vstmt = vstmt.where(Fact.id.notin_(found))
        vcols = (StateVersion.value_display, StateVersion.quote)
        more = await _ranked(s, vstmt, vcols, tsq, [], StateVersion.observed_at.desc(), limit * 3)
        for f, e in more:
            if f.id not in found and len(rows) < limit:
                rows.append((f, e))
                found.add(f.id)
    return [(f, e) for f, e in rows]


async def search_cards(s: AsyncSession, workspace_id: uuid.UUID, query: str, *, limit: int = 6):
    stmt = (select(IntelligenceReport, Entity).outerjoin(Entity, Entity.id == IntelligenceReport.entity_id)
            .where(IntelligenceReport.workspace_id == workspace_id))
    cols = (Entity.name, IntelligenceReport.title, IntelligenceReport.change_label, IntelligenceReport.area,
            IntelligenceReport.what_changed, IntelligenceReport.why_it_matters, IntelligenceReport.previous_state,
            IntelligenceReport.current_state, IntelligenceReport.evidence_summary)
    return await _ranked(s, stmt, cols, build_tsquery(query), like_patterns(query),
                         IntelligenceReport.detected_at.desc(), limit)


async def search_events(s: AsyncSession, workspace_id: uuid.UUID, query: str, *, limit: int = 6,
                        exclude: set[uuid.UUID] | None = None):
    """Events not already represented by a card (filtered noise is excluded)."""
    claims = (select(func.string_agg(Claim.statement, " ")).where(Claim.event_id == Event.id)
              .correlate(Event).scalar_subquery())
    stmt = (select(Event, Entity, IntelligenceReport.id).outerjoin(Entity, Entity.id == Event.entity_id)
            .outerjoin(IntelligenceReport, IntelligenceReport.event_id == Event.id)
            .where(Event.workspace_id == workspace_id, Event.status.notin_(("filtered", "failed"))))
    if exclude:
        stmt = stmt.where(Event.id.notin_(exclude))
    cols = (Entity.name, Event.title, Event.summary, Event.event_type, Event.area, Event.before_display,
            Event.after_display, claims)
    return await _ranked(s, stmt, cols, build_tsquery(query), like_patterns(query), Event.detected_at.desc(), limit)


async def search_entities(s: AsyncSession, workspace_id: uuid.UUID, query: str, *, limit: int = 5):
    stmt = select(Entity).where(Entity.workspace_id == workspace_id)
    cols = (Entity.name, cast(Entity.aliases, Text), Entity.description, Entity.role, Entity.kind,
            cast(Entity.official_domains, Text))
    rows = await _ranked(s, stmt, cols, build_tsquery(query), like_patterns(query), Entity.name, limit)
    return [r[0] for r in rows]


async def recent_versions(s: AsyncSession, fact_ids: list[uuid.UUID], per_fact: int = 4) -> dict[uuid.UUID, list[StateVersion]]:
    if not fact_ids:
        return {}
    rows = (await s.execute(select(StateVersion).where(StateVersion.fact_id.in_(fact_ids))
                            .order_by(StateVersion.fact_id, StateVersion.observed_at))).scalars().all()
    out: dict[uuid.UUID, list[StateVersion]] = {}
    for v in rows:
        out.setdefault(v.fact_id, []).append(v)
    return {k: v[-per_fact:] for k, v in out.items()}


def _trail(versions: list[StateVersion]) -> str:
    """Distinct consecutive values with the date each was first observed: "2026-01-04: 2% → 2026-08-02: 1.8%"."""
    parts, last = [], None
    for v in versions:
        if v.value_key != last:
            parts.append(f"{_d(v.valid_from or v.observed_at)}: {_clip(v.value_display, 80)}")
            last = v.value_key
    return " → ".join(parts)


def _fact_line(f: Fact, e: Entity, versions: list[StateVersion]) -> str:
    current = next((v for v in versions if v.id == f.current_version_id), versions[-1] if versions else None)
    value = (f"\"{_clip(current.value_display, 160)}\" (evidence: {current.evidence_status}, "
             f"observed {_d(current.observed_at)} via {current.observed_via})") if current else "not observed yet"
    line = f"[fact:{f.id}] {e.name} · {f.label} ({f.key}) = {value}"
    if f.last_changed_at:
        line += f"; last changed {_d(f.last_changed_at)}"
    trail = _trail(versions)
    if trail and len(versions) > 1:
        line += f"\n    history: {trail}"
    return line


def _card_line(r: IntelligenceReport, e: Entity | None) -> str:
    when = _d(r.occurred_at or r.detected_at)
    hist = " (reconstructed from web archive)" if r.is_historical else ""
    return (f"[card:{r.id}] {when}{hist} · {e.name if e else 'unknown entity'} · {r.change_label} · "
            f"severity {r.severity} · evidence {r.evidence_status}\n    {_clip(r.title, 200)}\n"
            f"    what changed (fact): {_clip(r.what_changed, 300)}")


# ---------------------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------------------


class SearchMemoryArgs(BaseModel):
    query: str = Field(description="names and topic words, e.g. 'Razorpay pricing fee' (not a whole sentence)")


class SearchMemoryTool(Tool):
    name = "search_memory"
    description = ("Full-text search of SignalLens memory for this workspace: tracked facts (current value and "
                   "value history with dates), intelligence cards (verified changes), other detected events, and "
                   "entities. Returns ids to cite.")
    Args = SearchMemoryArgs

    async def run(self, ctx: RunContext, args: SearchMemoryArgs) -> Observation:
        q = args.query.strip()
        if not q:
            return Observation.error("query is empty")
        async with ctx.services.session_factory() as s:
            facts = await search_facts(s, ctx.workspace_id, q)
            versions = await recent_versions(s, [f.id for f, _ in facts])
            cards = await search_cards(s, ctx.workspace_id, q)
            card_events = {r.event_id for r, _ in cards}
            events = await search_events(s, ctx.workspace_id, q, exclude=card_events)
            entities = await search_entities(s, ctx.workspace_id, q)
        sections = []
        if facts:
            sections.append("FACTS (tracked values; cite as fact)\n" + "\n".join(
                _fact_line(f, e, versions.get(f.id, [])) for f, e in facts))
        if cards:
            sections.append("INTELLIGENCE CARDS (verified changes; cite as card; open with get_card for evidence "
                            "and the assessment)\n" + "\n".join(_card_line(r, e) for r, e in cards))
        if events:
            sections.append("OTHER DETECTED EVENTS (cite as event, or its card if it has one)\n" + "\n".join(
                f"[event:{ev.id}] {_d(ev.occurred_at or ev.detected_at)} · {e.name if e else 'unknown entity'} · "
                f"{ev.event_type} · status {ev.status} · evidence {ev.evidence_status}\n    {_clip(ev.title, 200)}"
                + (f" — {_clip(ev.summary, 200)}" if ev.summary else "")
                + (f"\n    has card: [card:{rid}]" if rid else "")
                for ev, e, rid in events))
        if entities:
            sections.append("ENTITIES (cite as entity)\n" + "\n".join(
                f"[entity:{e.id}] {e.name} — {e.role} {e.kind}"
                + (f"; aliases: {', '.join(e.aliases)}" if e.aliases else "")
                + (f"; {_clip(e.description, 160)}" if e.description else "") for e in entities))
        for f, _ in facts:
            _seen(ctx, "fact", f.id)
        for r, _ in cards:
            _seen(ctx, "card", r.id)
            _seen(ctx, "event", r.event_id)
        for ev, _, rid in events:
            _seen(ctx, "event", ev.id)
            _seen(ctx, "card", rid)
        for e in entities:
            _seen(ctx, "entity", e.id)
        n = len(facts) + len(cards) + len(events) + len(entities)
        content = "\n\n".join(sections) if sections else (
            f"No matches in SignalLens memory for “{q}”. Try other names or fewer words, or recent_changes.")
        return Observation(
            ok=True, content=content, untrusted=True,
            summary=f"Searched memory: “{_clip(q, 80)}” → {len(facts)} facts, {len(cards)} cards, "
                    f"{len(events)} events, {len(entities)} entities",
            data={"query": q, "tsquery": build_tsquery(q), "matches": n,
                  "facts": [str(f.id) for f, _ in facts], "cards": [str(r.id) for r, _ in cards],
                  "events": [str(ev.id) for ev, _, _ in events], "entities": [str(e.id) for e in entities]},
        )


class FactIdArgs(BaseModel):
    fact_id: str = Field(description="fact id from search_memory or recent_changes")


class GetFactHistoryTool(Tool):
    name = "get_fact_history"
    description = "Every recorded value of one tracked fact, with observed/effective dates, evidence status and quotes."
    Args = FactIdArgs

    async def run(self, ctx: RunContext, args: FactIdArgs) -> Observation:
        fid = _uuid(args.fact_id)
        async with ctx.services.session_factory() as s:
            fact = await s.get(Fact, fid) if fid else None
            if fact is None or fact.workspace_id != ctx.workspace_id:
                return Observation.error(f"no fact with id {args.fact_id} in this workspace")
            entity = await s.get(Entity, fact.entity_id)
            versions = list((await s.execute(select(StateVersion).where(StateVersion.fact_id == fact.id)
                                              .order_by(StateVersion.observed_at))).scalars())
            event_ids = [v.event_id for v in versions if v.event_id]
            cards = dict((await s.execute(select(IntelligenceReport.event_id, IntelligenceReport.id).where(
                IntelligenceReport.event_id.in_(event_ids), IntelligenceReport.workspace_id == ctx.workspace_id
            ))).all()) if event_ids else {}
        lines = [f"[fact:{fact.id}] {entity.name if entity else '?'} · {fact.label} ({fact.key}), "
                 f"type {fact.value_type}, {len(versions)} observations"]
        for v in versions[-25:]:
            effective = f", effective {_d(v.valid_from)}" if v.valid_from else ""
            line = (f"- observed {_d(v.observed_at)} via {v.observed_via}{effective}: \"{_clip(v.value_display, 200)}\" "
                    f"(evidence: {v.evidence_status}{', current' if v.id == fact.current_version_id else ''})")
            if v.quote:
                line += f"\n    quote: “{_clip(v.quote, 240)}”"
            card = cards.get(v.event_id) if v.event_id else None
            if card:
                line += f"\n    change card: [card:{card}]"
                _seen(ctx, "card", card)
            lines.append(line)
        _seen(ctx, "fact", fact.id)
        _seen(ctx, "entity", fact.entity_id)
        return Observation(ok=True, content="\n".join(lines), untrusted=True,
                           summary=f"Read history of {entity.name if entity else ''} · {fact.label} ({len(versions)} values)",
                           data={"fact_id": str(fact.id), "versions": len(versions)})


class CardIdArgs(BaseModel):
    report_id: str = Field(description="card (intelligence report) id")


class GetCardTool(Tool):
    name = "get_card"
    description = ("One intelligence card in full: what changed (fact), previous/current state, evidence with quotes, "
                   "and why it matters (SignalLens's assessment, not fact).")
    Args = CardIdArgs

    async def run(self, ctx: RunContext, args: CardIdArgs) -> Observation:
        rid = _uuid(args.report_id)
        async with ctx.services.session_factory() as s:
            r = await s.get(IntelligenceReport, rid) if rid else None
            if r is None or r.workspace_id != ctx.workspace_id:
                return Observation.error(f"no card with id {args.report_id} in this workspace")
            entity = await s.get(Entity, r.entity_id) if r.entity_id else None
            event = await s.get(Event, r.event_id)
            evidence = (await s.execute(select(Evidence).join(Claim, Claim.id == Evidence.claim_id).where(
                Claim.event_id == r.event_id, Evidence.workspace_id == ctx.workspace_id)
                .order_by(Evidence.created_at).limit(8))).scalars().all()
            team_names = dict((await s.execute(select(Team.id, Team.name).where(Team.workspace_id == ctx.workspace_id))).all())
        teams = [team_names[t] for t in (_uuid(x) for x in (r.affected_team_ids or [])) if t in team_names]
        parts = [
            f"[card:{r.id}] {r.title}",
            f"entity: {entity.name if entity else 'unknown'}" + (f" [entity:{entity.id}]" if entity else ""),
            f"area: {r.area} · change: {r.change_label} · severity: {r.severity} · evidence status: {r.evidence_status}",
            f"detected {_d(r.detected_at)}; occurred/effective {_d(r.occurred_at) if r.occurred_at else 'unknown'}"
            + ("; reconstructed from web archive" if r.is_historical else ""),
            f"WHAT CHANGED (fact): {_clip(r.what_changed, 900)}",
        ]
        if r.previous_state or r.current_state:
            parts.append(f"BEFORE: {_clip(r.previous_state, 300) or 'n/a'}\nAFTER: {_clip(r.current_state, 300) or 'n/a'}")
        parts.append(f"WHY IT MATTERS (assessment, not fact): {_clip(r.why_it_matters, 900)}")
        if r.considerations:
            parts.append("Considerations (assessment): " + "; ".join(_clip(c, 200) for c in r.considerations[:5]))
        if r.assumptions:
            parts.append("Assumptions: " + "; ".join(_clip(c, 200) for c in r.assumptions[:5]))
        if teams:
            parts.append("Routed to teams: " + ", ".join(teams))
        if r.evidence_summary:
            parts.append(f"Evidence summary: {_clip(r.evidence_summary, 400)}")
        if evidence:
            parts.append("EVIDENCE:\n" + "\n".join(
                f"- [{e.stance}] {e.publisher} ({e.source_class}{', archived' if e.is_archive else ''}"
                f"{'' if e.quote_verified else ', quote NOT verified'}, {_d(e.published_at or e.retrieved_at)}): "
                f"“{_clip(e.quote, 300)}” {e.url}" for e in evidence))
        if event is not None and event.fact_id:
            parts.append(f"tracked fact: [fact:{event.fact_id}]")
            _seen(ctx, "fact", event.fact_id)
        _seen(ctx, "card", r.id)
        _seen(ctx, "event", r.event_id)
        _seen(ctx, "entity", r.entity_id)
        return Observation(ok=True, content="\n".join(parts), untrusted=True,
                           summary=f"Opened card: {_clip(r.title, 120)}",
                           data={"report_id": str(r.id), "evidence": len(evidence)})


class NoArgs(BaseModel):
    pass


class ListEntitiesTool(Tool):
    name = "list_entities"
    description = "All entities this workspace monitors (companies, regulators, products) with roles and counts."
    Args = NoArgs

    async def run(self, ctx: RunContext, args: NoArgs) -> Observation:
        async with ctx.services.session_factory() as s:
            ents = (await s.execute(select(Entity).where(Entity.workspace_id == ctx.workspace_id)
                                    .order_by(Entity.role, Entity.name))).scalars().all()
            facts = dict((await s.execute(select(Fact.entity_id, func.count(Fact.id)).where(
                Fact.workspace_id == ctx.workspace_id, Fact.active.is_(True)).group_by(Fact.entity_id))).all())
            cards = dict((await s.execute(select(IntelligenceReport.entity_id, func.count(IntelligenceReport.id)).where(
                IntelligenceReport.workspace_id == ctx.workspace_id).group_by(IntelligenceReport.entity_id))).all())
        for e in ents:
            _seen(ctx, "entity", e.id)
        lines = [f"[entity:{e.id}] {e.name} — {e.role} {e.kind}; {facts.get(e.id, 0)} tracked facts, "
                 f"{cards.get(e.id, 0)} cards" + (f"; domains: {', '.join(e.official_domains)}" if e.official_domains else "")
                 for e in ents]
        return Observation(ok=True, content="\n".join(lines) or "This workspace monitors no entities yet.",
                           summary=f"Listed {len(ents)} entities", data={"entities": len(ents)})


class RecentChangesArgs(BaseModel):
    days: int = Field(30, ge=1, le=730, description="look back this many days")
    entity: str | None = Field(None, description="entity name, optional")
    area: str | None = Field(None, description="area key or label, e.g. 'pricing', optional")
    team: str | None = Field(None, description="team name, e.g. 'Compliance' - cards routed to it, optional")


def _area_match(column: Any, keys: list[str]) -> ColumnElement:
    """Area keys differ between plans ("regulation" vs "regulation_compliance"): match by containment."""
    return or_(*[column.ilike(f"%{k.strip().lower().replace('_', ' ').split()[0]}%") for k in keys if k.strip()])


class RecentChangesTool(Tool):
    name = "recent_changes"
    description = ("What changed in a time window, newest first: intelligence cards, other detected events, and "
                   "tracked-fact value changes. Filter by entity, area or team.")
    Args = RecentChangesArgs

    async def run(self, ctx: RunContext, args: RecentChangesArgs) -> Observation:
        since = utcnow() - timedelta(days=args.days)
        wid = ctx.workspace_id
        async with ctx.services.session_factory() as s:
            when = func.coalesce(IntelligenceReport.occurred_at, IntelligenceReport.detected_at)
            ev_when = func.coalesce(Event.occurred_at, Event.detected_at)
            cq = (select(IntelligenceReport, Entity).outerjoin(Entity, Entity.id == IntelligenceReport.entity_id)
                  .where(IntelligenceReport.workspace_id == wid, when >= since))
            has_card = select(IntelligenceReport.id).where(IntelligenceReport.event_id == Event.id).exists()
            eq = (select(Event, Entity).outerjoin(Entity, Entity.id == Event.entity_id)
                  .where(Event.workspace_id == wid, ev_when >= since, Event.status.notin_(("filtered", "failed")),
                         ~has_card))
            fq = (select(Fact, Entity).join(Entity, Entity.id == Fact.entity_id)
                  .where(Fact.workspace_id == wid, Fact.active.is_(True), Fact.last_changed_at >= since))
            if args.entity:
                pat = f"%{args.entity.strip()}%"
                ent_match = or_(Entity.name.ilike(pat), cast(Entity.aliases, Text).ilike(pat))
                cq, eq, fq = cq.where(ent_match), eq.where(ent_match), fq.where(ent_match)
            if args.area:
                a = args.area.strip()
                cq = cq.where(or_(_area_match(IntelligenceReport.area, [a]), IntelligenceReport.change_label.ilike(f"%{a}%")))
                eq = eq.where(or_(_area_match(Event.area, [a]), Event.event_type.ilike(f"%{a}%")))
                fq = fq.where(_area_match(Fact.area, [a]))
            if args.team:
                team = (await s.execute(select(Team).where(Team.workspace_id == wid, Team.name.ilike(f"%{args.team.strip()}%"))
                                        .limit(1))).scalar_one_or_none()
                if team is None:
                    names = (await s.execute(select(Team.name).where(Team.workspace_id == wid))).scalars().all()
                    return Observation.error(f"no team matching '{args.team}'. Teams: {', '.join(names) or 'none'}")
                areas = list(team.areas or [])
                conds = [IntelligenceReport.affected_team_ids.contains([str(team.id)])]
                if areas:
                    conds.append(_area_match(IntelligenceReport.area, areas))
                cq = cq.where(or_(*conds))
                eq = eq.where(_area_match(Event.area, areas)) if areas else eq.where(Event.id.is_(None))
                fq = fq.where(_area_match(Fact.area, areas)) if areas else fq.where(Fact.id.is_(None))
            cards = (await s.execute(cq.order_by(when.desc()).limit(12))).all()
            events = (await s.execute(eq.order_by(ev_when.desc()).limit(10))).all()
            facts = (await s.execute(fq.order_by(Fact.last_changed_at.desc()).limit(10))).all()
            versions = await recent_versions(s, [f.id for f, _ in facts], per_fact=3)
        for r, _ in cards:
            _seen(ctx, "card", r.id)
            _seen(ctx, "event", r.event_id)
        for ev, _ in events:
            _seen(ctx, "event", ev.id)
        for f, _ in facts:
            _seen(ctx, "fact", f.id)
        filters = ", ".join(f"{k}={v}" for k, v in (("entity", args.entity), ("area", args.area), ("team", args.team)) if v)
        head = f"Changes since {since.date().isoformat()} (last {args.days} days{'; ' + filters if filters else ''})"
        sections = [head]
        if cards:
            sections.append("CARDS\n" + "\n".join(_card_line(r, e) for r, e in cards))
        if events:
            sections.append("OTHER DETECTED EVENTS (no card yet; cite as event)\n" + "\n".join(
                f"[event:{ev.id}] {_d(ev.occurred_at or ev.detected_at)} · {e.name if e else 'unknown entity'} · "
                f"{ev.area} · {ev.event_type} · status {ev.status} · evidence {ev.evidence_status}"
                + (" (reconstructed from web archive)" if ev.is_historical else "")
                + f"\n    {_clip(ev.title, 200)}" + (f" — {_clip(ev.summary, 200)}" if ev.summary else "")
                for ev, e in events))
        if facts:
            sections.append("FACT VALUE CHANGES\n" + "\n".join(_fact_line(f, e, versions.get(f.id, [])) for f, e in facts))
        if not (cards or events or facts):
            sections.append("Nothing recorded in this window.")
        return Observation(ok=True, content="\n\n".join(sections), untrusted=True,
                           summary=f"Listed changes in the last {args.days} days{' (' + filters + ')' if filters else ''}: "
                                   f"{len(cards)} cards, {len(events)} events, {len(facts)} fact changes",
                           data={"cards": [str(r.id) for r, _ in cards], "events": [str(ev.id) for ev, _ in events],
                                 "facts": [str(f.id) for f, _ in facts]})


class WebSearchArgs(BaseModel):
    query: str = Field(description="web search query")


WEB_LABEL = "OUTSIDE SIGNALLENS MEMORY — NOT VERIFIED"


class AskWebSearchTool(Tool):
    name = "web_search"
    description = ("Web search, ONLY when memory has no answer. Results are outside SignalLens memory and not "
                   "verified; label them so in the answer and cite them with kind 'web' and the URL as id.")
    Args = WebSearchArgs

    async def run(self, ctx: RunContext, args: WebSearchArgs) -> Observation:
        try:
            results = await ctx.services.require_search().search(args.query, max_results=5, topic="general")
        except SearchError as e:
            return Observation.error(f"search failed: {e}")
        urls: dict[str, str] = ctx.scratch.setdefault("web_urls", {})
        lines = [WEB_LABEL]
        for r in results:
            urls[r.url] = r.title or r.publisher or r.url
            when = r.published_at.date().isoformat() if r.published_at else "date unknown"
            lines.append(f"[web:{r.url}] {r.title} — {r.publisher} — {when}\n    {_clip(r.snippet, 300)}")
            _seen(ctx, "web", r.url)
        return Observation(ok=True, content="\n".join(lines) if results else "No web results.", untrusted=True,
                           summary=f"Searched the web (outside memory): “{_clip(args.query, 80)}” → {len(results)} results",
                           data={"query": args.query, "results": [{"title": r.title, "url": r.url} for r in results]})


__all__ = [
    "AskWebSearchTool",
    "GetCardTool",
    "GetFactHistoryTool",
    "ListEntitiesTool",
    "RecentChangesTool",
    "SearchMemoryTool",
    "build_tsquery",
    "like_patterns",
    "search_terms",
]

