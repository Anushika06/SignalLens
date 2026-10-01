"""Phase 1: request → research → proposed plan → live validation → waiting for approval."""

from __future__ import annotations

import asyncio
import logging
import uuid

from signallens.agents.planner import PlannerAgent, compose_plan, research_task
from signallens.agents.schemas import MonitoringPlanOut
from signallens.db.models import MonitoringPolicy, Workspace
from signallens.db.session import transaction
from signallens.domain.clustering import slug
from signallens.fetch.extract import extract_result
from signallens.fetch.render import render_if_js_shell
from signallens.pipeline.common import team_names, today_str
from signallens.plan import (
    MonitoringPlan,
    PlanArea,
    PlanAttribute,
    PlanDomain,
    PlanEntity,
    PlanSource,
    SourceValidation,
)
from signallens.runtime.core import Budget, finish_run, start_run
from signallens.runtime.services import Services
from signallens.util.urls import host_of

log = logging.getLogger(__name__)


async def run_planning(services: Services, policy_id: uuid.UUID) -> None:
    async with services.session_factory() as s:
        policy = await s.get(MonitoringPolicy, policy_id)
        if policy is None or policy.status != "planning":
            return
        ws = await s.get(Workspace, policy.workspace_id)
        teams = await team_names(s, policy.workspace_id)
        profile, request_text, workspace_id = dict(ws.profile or {}), policy.request_text, ws.id

    settings = services.settings
    ctx = await start_run(
        services, workspace_id=workspace_id, agent="planner", title=f"Plan: {request_text[:80]}",
        task={"request": request_text}, subject_type="policy", subject_id=policy_id,
        budget=Budget(max_steps=settings.planner_max_steps, max_tool_calls=settings.planner_max_steps + 2,
                      max_llm_calls=settings.planner_max_steps + 6, max_seconds=420,
                      max_cost_usd=settings.planner_max_cost_usd),
    )
    async with transaction(services.session_factory) as s:
        p = await s.get(MonitoringPolicy, policy_id)
        p.planner_run_id = ctx.run_id
    try:
        agent = PlannerAgent(search_available=services.search is not None)
        today = today_str()
        loop = await agent.run(ctx, research_task(request_text, profile, today))
        notes = loop.final.notes if loop.final is not None else (
            "Research stopped early (budget). Use the research log below.")
        # Composing is allowed a little beyond the research budget: it is one call.
        ctx.budget.max_llm_calls += 2
        ctx.budget.max_cost_usd += 0.25
        draft = await compose_plan(ctx, request_text=request_text, profile=profile, team_names=teams, notes=notes,
                                   research_log=loop.research_log, today=today)
        plan = normalize_plan(draft, teams)
        await ctx.step("note", f"Validating {len(plan.sources)} proposed sources live", name="validate_sources")
        await validate_sources(services, plan)
        ok = sum(1 for src in plan.sources if src.validation and src.validation.ok)
        await ctx.step("state_update", f"Plan ready: {len(plan.entities)} entities, {len(plan.areas)} areas, "
                                       f"{len(plan.sources)} sources ({ok} validated)", name="plan")
        async with transaction(services.session_factory) as s:
            p = await s.get(MonitoringPolicy, policy_id)
            p.spec = plan.model_dump(mode="json")
            p.status = "pending_approval"
            w = await s.get(Workspace, workspace_id)
            w.status = "awaiting_approval"
        await finish_run(ctx, "succeeded", result={"summary": plan.summary, "sources": len(plan.sources)})
    except Exception as e:
        log.exception("planning failed")
        async with transaction(services.session_factory) as s:
            p = await s.get(MonitoringPolicy, policy_id)
            p.status, p.error = "failed", f"{type(e).__name__}: {e}"[:2000]
            w = await s.get(Workspace, workspace_id)
            w.status = "setup"
        await finish_run(ctx, "failed", error=str(e))


def _unique(base: str, used: set[str]) -> str:
    candidate, i = base or "item", 2
    while candidate in used:
        candidate, i = f"{base}-{i}", i + 1
    used.add(candidate)
    return candidate


def normalize_plan(draft: MonitoringPlanOut, teams: list[str]) -> MonitoringPlan:
    """Make the model's draft internally consistent (refs, keys, bounds, team names)."""
    team_lookup = {t.lower(): t for t in teams}
    used_refs: set[str] = set()
    ref_map: dict[str, str] = {}
    entities: list[PlanEntity] = []
    for e in draft.entities:
        ref = _unique(slug(e.ref or e.name, max_len=40), used_refs)
        ref_map[e.ref] = ref
        ref_map.setdefault(slug(e.name, max_len=40), ref)
        domains = sorted({host_of(d).removeprefix("www.") for d in e.official_domains if d and "." in d})
        entities.append(PlanEntity(ref=ref, name=e.name.strip(), kind=e.kind, role=e.role, aliases=e.aliases[:8],
                                   official_domains=domains, description=e.description, reason=e.reason))
    subject_ref = next((e.ref for e in entities if e.role == "subject"), entities[0].ref if entities else "subject")

    used_areas: set[str] = set()
    areas: list[PlanArea] = []
    for a in draft.areas:
        key = _unique(slug(a.key, max_len=30).replace("-", "_"), used_areas)
        routes = [team_lookup[t.lower()] for t in a.route_to if t.lower() in team_lookup] or teams[:1]
        areas.append(PlanArea(key=key, label=a.label, description=a.description, importance=a.importance,
                              reason=a.reason, route_to=routes))
    area_keys = {a.key for a in areas}
    area_alias = {slug(a.key, max_len=30).replace("-", "_"): a.key for a in areas}

    def fix_area(k: str) -> str:
        k2 = slug(k, max_len=30).replace("-", "_")
        return area_alias.get(k2, k2 if k2 in area_keys else (areas[0].key if areas else "general"))

    used_src: set[str] = set()
    src_map: dict[str, str] = {}
    sources: list[PlanSource] = []
    for src in draft.sources:
        if src.kind == "page" and not (src.url or "").startswith(("http://", "https://", "sandbox://")):
            continue
        if src.kind == "news" and not (src.query or "").strip():
            continue
        ref = _unique(slug(src.ref or src.url or src.query, max_len=40), used_src)
        src_map[src.ref] = ref
        src_areas = sorted({fix_area(a) for a in src.areas})
        if not src_areas and areas:
            src_areas = [areas[0].key]
        sources.append(PlanSource(
            ref=ref, kind=src.kind, url=src.url if src.kind == "page" else None,
            query=src.query.strip() if src.kind == "news" and src.query else None,
            entity_ref=ref_map.get(src.entity_ref, ref_map.get(slug(src.entity_ref, max_len=40), subject_ref)),
            areas=src_areas,
            authority=src.authority, priority=src.priority,
            check_every_hours=max(1.0, min(168.0, float(src.check_every_hours or 12))),
            backfill=bool(src.backfill and src.kind == "page"), reason=src.reason,
        ))

    used_keys: set[str] = set()
    attributes: list[PlanAttribute] = []
    for at in draft.attributes:
        area = fix_area(at.area)
        key_tail = slug(at.key.split(".", 1)[-1], max_len=50).replace("-", "_")
        key = _unique(f"{area}.{key_tail}", used_keys)
        refs = [src_map[r] for r in at.source_refs if r in src_map] or [
            s.ref for s in sources if s.kind == "page" and area in s.areas][:2]
        attributes.append(PlanAttribute(
            key=key, entity_ref=ref_map.get(at.entity_ref, subject_ref), area=area, label=at.label,
            value_type=at.value_type, hint=at.hint, source_refs=refs,
        ))

    return MonitoringPlan(
        summary=draft.summary,
        domain=PlanDomain(**draft.domain.model_dump()),
        entities=entities, areas=areas, attributes=attributes, sources=sources,
        open_questions=draft.open_questions[:5],
    )


async def validate_sources(services: Services, plan: MonitoringPlan) -> None:
    """Check each proposed source live so the human approves with facts, not guesses (C17)."""

    async def check(src: PlanSource) -> None:
        if src.kind == "page":
            fr = await services.fetcher.fetch(src.url)
            if fr.blocked == "robots":
                src.validation = SourceValidation(ok=False, robots_allowed=False,
                                                  note="Disallowed by the site's robots.txt; SignalLens won't fetch it.")
                src.enabled = False
                return
            if fr.blocked:
                src.validation = SourceValidation(ok=False, note=f"Not fetched: {fr.blocked}")
                src.enabled = False
                return
            if not fr.ok:
                src.validation = SourceValidation(ok=False, http_status=fr.status, robots_allowed=True,
                                                  note=fr.error or f"HTTP {fr.status}")
                src.enabled = False
                return
            ext = extract_result(fr, mode="page")
            st = services.settings
            rendered = await render_if_js_shell(
                fr, ext, enabled=st.render_js, timeout_s=st.render_timeout_s, user_agent=st.user_agent,
                allow_private=bool(getattr(services.fetcher, "allow_private_hosts", False)),
                max_bytes=st.fetch_max_bytes, renderer=services.extras.get("renderer"),
            )
            ext = rendered.doc
            ok = ext.quality == "ok"
            src.validation = SourceValidation(
                ok=ok, http_status=fr.status, robots_allowed=True, quality=ext.quality, title=ext.title,
                note=(rendered.note if rendered.rendered else None) if ok
                else (ext.quality_reason or "Page content looks empty or blocked"),
            )
            src.enabled = ok
        else:
            if services.search is None:
                src.validation = SourceValidation(ok=False, note="Not checked: no search provider configured.")
                return
            try:
                results = await services.search.search(src.query or "", max_results=3, recency_days=30, topic="news")
            except Exception as e:  # provider hiccup should not block planning
                src.validation = SourceValidation(ok=False, note=f"Search failed: {e}")
                return
            src.validation = SourceValidation(
                ok=bool(results), note=f"{len(results)} recent article(s) found" if results else "No recent articles found",
            )

    await asyncio.gather(*(check(src) for src in plan.sources))
