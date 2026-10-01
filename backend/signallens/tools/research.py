"""Read-only research tools: search, open pages, look into the web archive, read our history.

Pages an agent opens are remembered in the run context; they are the only documents it
may later quote as evidence.
"""

from __future__ import annotations

from datetime import date, timedelta

from pydantic import BaseModel, Field
from sqlalchemy import select

from signallens.db.base import utcnow
from signallens.db.models import Entity, Fact
from signallens.db.session import transaction
from signallens.fetch.extract import extract_result
from signallens.runtime.core import Observation, RetrievedDoc, RunContext, Tool
from signallens.search.base import SearchError
from signallens.store.documents import publisher_of, save_document
from signallens.store.world import history
from signallens.util.text import window_around

EXCERPT_CHARS = 4500


def _format_results(results) -> str:
    if not results:
        return "No results."
    lines = []
    for i, r in enumerate(results, 1):
        when = r.published_at.date().isoformat() if r.published_at else "date unknown"
        snippet = " ".join((r.snippet or "").split())[:300]
        lines.append(f"[{i}] {r.title} — {r.publisher} — {when}\n    {r.url}\n    {snippet}")
    return "\n".join(lines)


class SearchArgs(BaseModel):
    query: str = Field(description="search query")
    recency_days: int | None = Field(None, ge=1, le=3650, description="only results from the last N days")
    domains: list[str] | None = Field(None, description="restrict to these domains, e.g. ['razorpay.com']")


class SearchWebTool(Tool):
    name = "search_web"
    description = ("Web search. Returns numbered results (title, publisher, date, URL, snippet). "
                   "Snippets are leads, not evidence - open a page before quoting it.")
    Args = SearchArgs

    async def run(self, ctx: RunContext, args: SearchArgs) -> Observation:
        try:
            results = await ctx.services.require_search().search(
                args.query, max_results=8, recency_days=args.recency_days, include_domains=args.domains,
                topic="general",
            )
        except SearchError as e:
            return Observation.error(f"search failed: {e}")
        return Observation(
            ok=True, content=_format_results(results), untrusted=True,
            summary=f"Searched the web: “{args.query}” → {len(results)} results",
            data={"query": args.query, "results": [{"title": r.title, "url": r.url, "publisher": r.publisher,
                                                     "published_at": r.published_at} for r in results]},
        )


class SearchNewsArgs(BaseModel):
    query: str = Field(description="news search query")
    recency_days: int = Field(30, ge=1, le=365, description="only articles from the last N days")


class SearchNewsTool(Tool):
    name = "search_news"
    description = ("News search. Returns numbered articles (title, publisher, date, URL, snippet). "
                   "Open an article before quoting it.")
    Args = SearchNewsArgs

    async def run(self, ctx: RunContext, args: SearchNewsArgs) -> Observation:
        try:
            results = await ctx.services.require_search().search(
                args.query, max_results=8, recency_days=args.recency_days, topic="news"
            )
        except SearchError as e:
            return Observation.error(f"news search failed: {e}")
        return Observation(
            ok=True, content=_format_results(results), untrusted=True,
            summary=f"Searched news: “{args.query}” (last {args.recency_days} days) → {len(results)} articles",
            data={"query": args.query, "results": [{"title": r.title, "url": r.url, "publisher": r.publisher,
                                                     "published_at": r.published_at} for r in results]},
        )


class OpenPageArgs(BaseModel):
    url: str = Field(description="absolute URL to open")
    focus: list[str] = Field(default_factory=list, description="optional keywords; the excerpt centres on them")


def _excerpt(doc: RetrievedDoc, focus: list[str]) -> str:
    body = window_around(doc.text, focus, max_chars=EXCERPT_CHARS) if focus else doc.text[:EXCERPT_CHARS]
    head = (f"TITLE: {doc.title or '(none)'}\nPUBLISHER: {doc.publisher}\n"
            f"PUBLISHED: {doc.published_at.date().isoformat() if doc.published_at else 'unknown'}\n"
            f"URL: {doc.final_url}\nLENGTH: {len(doc.text.split())} words\n---\n")
    return head + body


class OpenPageTool(Tool):
    name = "open_page"
    description = ("Fetch a web page (respecting robots.txt) and return its main text, centred on `focus` "
                   "keywords if given. Opening a page is what makes it quotable as evidence.")
    Args = OpenPageArgs
    timeout_s = 60.0

    async def run(self, ctx: RunContext, args: OpenPageArgs) -> Observation:
        doc = ctx.recall(args.url)
        if doc is None:
            fr = await ctx.services.fetcher.fetch(args.url)
            if fr.blocked:
                return Observation.error(f"not fetched ({fr.blocked}): {args.url}")
            if not fr.ok:
                return Observation.error(f"could not open {args.url}: HTTP {fr.status} {fr.error or ''}".strip())
            ext = extract_result(fr, mode="article")
            if ext.word_count < 120:
                page = extract_result(fr, mode="page")
                if page.word_count > ext.word_count:
                    ext = page
            if ext.quality == "blocked":
                return Observation.error(f"{args.url} returned an anti-bot or access-denied page")
            async with transaction(ctx.services.session_factory) as s:
                stored = await save_document(s, workspace_id=ctx.workspace_id, url=args.url, extracted=ext, fetch=fr)
            doc = RetrievedDoc(url=args.url, final_url=fr.final_url or args.url, title=ext.title,
                               publisher=publisher_of(fr.final_url or args.url), text=ext.text,
                               published_at=ext.published_at, document_id=stored.id)
            ctx.remember(doc)
        return Observation(
            ok=True, content=_excerpt(doc, args.focus), untrusted=True,
            summary=f"Opened {doc.publisher}: {(doc.title or doc.final_url)[:120]}",
            data={"url": doc.final_url, "title": doc.title, "publisher": doc.publisher,
                  "words": len(doc.text.split()), "focus": args.focus},
        )


class ArchiveListArgs(BaseModel):
    url: str
    since: str | None = Field(None, description="ISO date, e.g. 2025-01-01")
    until: str | None = Field(None, description="ISO date")


class ListArchiveCapturesTool(Tool):
    name = "list_archive_captures"
    description = "List monthly Internet Archive captures of a URL (to see what a page said in the past)."
    Args = ArchiveListArgs

    async def run(self, ctx: RunContext, args: ArchiveListArgs) -> Observation:
        since = date.fromisoformat(args.since) if args.since else (utcnow() - timedelta(days=400)).date()
        until = date.fromisoformat(args.until) if args.until else None
        try:
            caps = await ctx.services.wayback.list_captures(args.url, since=since, until=until, per="month", limit=24)
        except Exception as e:
            return Observation.error(f"archive lookup failed: {e}")
        lines = [f"{c.timestamp} ({c.captured_at.date().isoformat()})" for c in caps]
        return Observation(ok=True, content="\n".join(lines) or "No captures found.",
                           summary=f"Listed {len(caps)} archive captures of {args.url}",
                           data={"url": args.url, "captures": [c.timestamp for c in caps]})


class OpenArchivedArgs(BaseModel):
    url: str
    timestamp: str = Field(description="capture timestamp from list_archive_captures, e.g. 20250321031539")
    focus: list[str] = Field(default_factory=list)


class OpenArchivedPageTool(Tool):
    name = "open_archived_page"
    description = "Open a past capture of a page from the Internet Archive. Quotable as (archived) evidence."
    Args = OpenArchivedArgs
    timeout_s = 90.0

    async def run(self, ctx: RunContext, args: OpenArchivedArgs) -> Observation:
        from signallens.fetch.wayback import ArchiveCapture  # local import keeps tool import cheap

        caps = await ctx.services.wayback.list_captures(args.url, per="all", limit=200,
                                                        since=_ts_date(args.timestamp), until=_ts_date(args.timestamp))
        cap = next((c for c in caps if c.timestamp == args.timestamp), None) or (caps[0] if caps else None)
        if cap is None:
            cap = ArchiveCapture(timestamp=args.timestamp, captured_at=_ts_datetime(args.timestamp),
                                 original_url=args.url, status=200, digest=None, length=None)
        doc = ctx.recall(cap.archive_url)
        if doc is None:
            fr = await ctx.services.wayback.fetch_capture(cap)
            if not fr.ok:
                return Observation.error(f"could not open archived capture: HTTP {fr.status} {fr.error or ''}")
            ext = extract_result(fr, mode="page")
            async with transaction(ctx.services.session_factory) as s:
                stored = await save_document(s, workspace_id=ctx.workspace_id, url=cap.archive_url, extracted=ext,
                                             fetch=fr, origin="archive", archive_timestamp=cap.timestamp,
                                             published_at=cap.captured_at)
            doc = RetrievedDoc(url=cap.archive_url, final_url=cap.archive_url, title=ext.title,
                               publisher=publisher_of(args.url), text=ext.text, published_at=cap.captured_at,
                               document_id=stored.id, is_archive=True)
            ctx.remember(doc)
        return Observation(ok=True, content=_excerpt(doc, args.focus), untrusted=True,
                           summary=f"Opened archived {args.url} as of {cap.captured_at.date().isoformat()}",
                           data={"archive_url": cap.archive_url})


def _ts_date(ts: str) -> date | None:
    try:
        return date(int(ts[0:4]), int(ts[4:6]), int(ts[6:8]))
    except (ValueError, IndexError):
        return None


def _ts_datetime(ts: str):
    from datetime import UTC, datetime

    return datetime.strptime(ts[:14].ljust(14, "0"), "%Y%m%d%H%M%S").replace(tzinfo=UTC)


class FactHistoryArgs(BaseModel):
    entity: str | None = Field(None, description="entity name")
    key: str | None = Field(None, description="fact key, e.g. pricing.standard_domestic_fee")


class FactHistoryTool(Tool):
    name = "get_fact_history"
    description = "Look up what SignalLens already knows: tracked facts and how their values changed over time."
    Args = FactHistoryArgs

    async def run(self, ctx: RunContext, args: FactHistoryArgs) -> Observation:
        async with ctx.services.session_factory() as s:
            q = select(Fact, Entity).join(Entity, Entity.id == Fact.entity_id).where(Fact.workspace_id == ctx.workspace_id)
            if args.key:
                q = q.where(Fact.key == args.key)
            if args.entity:
                q = q.where(Entity.name.ilike(f"%{args.entity}%"))
            rows = (await s.execute(q.limit(12))).all()
            lines = []
            for fact, ent in rows:
                versions = await history(s, fact.id)
                trail = " → ".join(f"{v.observed_at.date().isoformat()}: {v.value_display}" for v in versions[-6:])
                lines.append(f"{ent.name} · {fact.label} ({fact.key}): {trail or 'no observations yet'}")
        return Observation(ok=True, content="\n".join(lines) or "No matching facts.",
                           summary=f"Checked world-state history ({len(lines)} facts)")
