"""The one-shot intelligence brief agent ("tell me about Razorpay, for Cashfree").

The full product monitors continuously and keeps its memory in PostgreSQL. A brief is the
same judgment compressed into one bounded run with no database, so it can also execute in
a throwaway aiKart container:

1. **Resolve** - web search, a heuristic guess of the official domain, a site map search,
   then the reasoning model picks the official domain and 3-5 official pages (with reasons).
2. **Read** - the pages are read (directly or through Tavily Extract, see
   :mod:`signallens.brief.reader`); the fast model extracts focus-dependent facts with
   verbatim quotes; code drops every quote that does not occur in the page text.
3. **History** - for up to three stable pages (pricing first), the Wayback capture closest to
   ``months_back`` ago (after the snapshot quality gate) is compared with today's page.
   Before/after values are compared by code; a quote must verify on each side.
4. **News** - recent news and the company's own press items are triaged by the fast model
   (relevance, story grouping, a supporting quote); code verifies quotes and computes the
   evidence status with :func:`signallens.domain.evidence.assess`.
5. **Impact** - the reasoning model writes why it matters to the requester, separating
   cited facts from assessment, with three owned actions.
6. **Render** - :mod:`signallens.brief.render`.

Every stage runs under a slice of the overall deadline and degrades instead of failing:
a brief with fewer sections is always better than no brief. Model calls go through one
semaphore (NVIDIA NIM's free tier allows ~40 requests/minute and queues bursts).
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections import Counter
from datetime import UTC, date, datetime, timedelta
from typing import Any, TypeVar

from pydantic import BaseModel
from rapidfuzz import fuzz

from signallens.brief import prompts
from signallens.brief.models import BriefInput, BriefResult
from signallens.brief.reader import PageReader, ReadPage, make_reader, reader_mode
from signallens.brief.render import render_markdown
from signallens.brief.schemas import (
    CompanyNameOut,
    ExtractOut,
    HistoryOut,
    ImpactOut,
    ResolveOut,
    TriageOut,
)
from signallens.brief.state import (
    STATUS_LABELS,
    BriefState,
    Change,
    Company,
    Fact,
    PageInfo,
    Source,
    Story,
)
from signallens.brief.trace import Deadline, Step, StepCallback, Trace
from signallens.domain.clustering import slug
from signallens.domain.evidence import COMMUNITY_DOMAINS, EvidenceItem, assess, classify_source
from signallens.fetch.extract import ExtractedDoc, extract_result
from signallens.search.base import SearchResult
from signallens.util.text import normalize_for_match, quote_in_text, truncate, window_around
from signallens.util.urls import domain_matches, host_of, normalize_url, registrable_domain

log = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

# "Recent" news. Search providers return sparse, slightly stale news coverage, so a strict 90 days
# misses landmark items (an IPO filing 100 days ago); four months keeps them.
NEWS_WINDOW_DAYS = 120
MAX_PAGES = 5
HISTORY_PAGES = 3
LLM_CONCURRENCY = 4
PAGE_CHARS = 9000
HISTORY_CHARS = 6500
IMPACT_RESERVE_S = 70.0  # kept free for the impact call + rendering
MIN_CALL_S = 8.0
STORY_MERGE_SIMILARITY = 75

# Sites that describe companies but are never a company's own domain.
NOT_OFFICIAL = (
    *COMMUNITY_DOMAINS, "wikipedia.org", "crunchbase.com", "tracxn.com", "glassdoor.com", "glassdoor.co.in",
    "ambitionbox.com", "zaubacorp.com", "tofler.in", "pitchbook.com", "bloomberg.com", "reuters.com",
    "economictimes.com", "indiatimes.com", "livemint.com", "moneycontrol.com", "inc42.com", "yourstory.com",
    "techcrunch.com", "forbes.com", "g2.com", "capterra.com", "trustpilot.com", "play.google.com", "apple.com",
    "github.com", "zoominfo.com", "owler.com", "cbinsights.com", "craft.co", "similarweb.com", "leadiq.com",
    "rocketreach.co", "apollo.io", "signalhire.com", "contactout.com", "cloudfront.net", "amazonaws.com",
    "reveliolabs.com", "growjo.com", "datanyze.com", "6sense.com", "builtwith.com", "wellfound.com",
)

SITE_QUERY_BY_FOCUS = {
    "Everything": "pricing products plans",
    "Pricing & products": "pricing fees plans products",
    "Regulatory & compliance": "terms policy compliance grievance",
    "Partnerships & funding": "partners integrations investors",
    "Leadership & hiring": "leadership team careers",
}
NEWS_QUERY_BY_FOCUS = {
    "Everything": "launch partnership funding regulation",
    "Pricing & products": "pricing fees new product launch",
    "Regulatory & compliance": "regulator compliance licence penalty",
    "Partnerships & funding": "partnership funding investment acquisition",
    "Leadership & hiring": "appoints CEO executive hiring layoffs",
}
# Pages whose history is worth reconstructing (newsrooms and careers pages change by design).
HISTORY_KIND_ORDER = ("pricing", "products", "legal", "about", "homepage", "investors", "other")

COMMON_TLDS = frozenset({"com", "in", "co.in", "io", "co", "ai", "org", "net", "app", "tech", "co.uk", "de", "fr"})

_URLISH = re.compile(r"^(https?://)?([a-z0-9-]+\.)+[a-z]{2,}(/\S*)?$", re.I)
_NUMBER = re.compile(r"\d+(?:[.,]\d+)*")


class StageSkipped(Exception):
    """Not enough time left for this stage."""


class _Models:
    """Bounded, counted access to the model gateway for one run."""

    def __init__(self, gateway, trace: Trace, deadline: Deadline, concurrency: int = LLM_CONCURRENCY):
        self.gateway = gateway
        self.trace = trace
        self.deadline = deadline
        self._sem = asyncio.Semaphore(concurrency)

    async def call(self, schema: type[T], *, step: Step, tier: str, system: str, prompt: str, purpose: str,
                   cap_s: float, reserve_s: float = 0.0, max_tokens: int = 4000) -> T:
        async with self._sem:
            budget = self.deadline.slice(cap_s, reserve=reserve_s)
            if budget < MIN_CALL_S * self.deadline.scale:
                raise StageSkipped(f"{purpose}: not enough time left")
            call = getattr(self.gateway, "structured_with_meta", None)
            step.model_calls += 1
            self.trace.model_calls += 1
            if call is not None:
                obj, meta = await asyncio.wait_for(
                    call(schema, tier=tier, system=system, messages=prompt, ctx=None, purpose=purpose,
                         max_tokens=max_tokens),
                    budget,
                )
                self.trace.input_tokens += meta.input_tokens
                self.trace.output_tokens += meta.output_tokens
                return obj
            return await asyncio.wait_for(
                self.gateway.structured(schema, tier=tier, system=system, messages=prompt, ctx=None), budget)


async def _gather_limited(coros, limit_s: float) -> list[Any]:
    """Run coroutines concurrently; exceptions and timeouts come back as values."""
    if limit_s <= 0:
        for c in coros:
            c.close()
        return [StageSkipped("no time left")] * len(coros)
    tasks = [asyncio.ensure_future(c) for c in coros]
    done, pending = await asyncio.wait(tasks, timeout=limit_s) if tasks else (set(), set())
    for t in pending:
        t.cancel()
    out = []
    for t in tasks:
        if t in done:
            out.append(t.exception() if t.exception() is not None else t.result())
        else:
            out.append(TimeoutError("timed out"))
    return out


def _fence(text: str) -> str:
    return f"<untrusted_content>\n{text}\n</untrusted_content>"


def _numbers(s: str) -> set[str]:
    return {m.group(0).replace(",", "") for m in _NUMBER.finditer(s or "")}


def looks_like_request(text: str) -> bool:
    """Free text ("what is Razorpay up to?") rather than a company name or website."""
    t = text.strip().lower()
    return len(t.split()) > 5 or "?" in t or t.startswith(
        ("what", "tell", "how", "give", "brief", "analy", "show", "who", "research", "monitor", "please"))


def _site_label(domain: str) -> str:
    return slug(domain.split(".")[0]).replace("-", "")


def guess_domain(company: str, results: list[SearchResult]) -> str | None:
    """Heuristic official domain: a non-directory domain whose label matches the company name."""
    if _URLISH.match(company.strip()):
        return registrable_domain(company.strip())
    name = slug(company, strip_suffixes=True).replace("-", "")
    first_word = slug(company, strip_suffixes=True).split("-")[0] if company.strip() else ""
    scores: Counter[str] = Counter()
    for rank, r in enumerate(results):
        d = registrable_domain(r.url)
        if not d or domain_matches(r.url, NOT_OFFICIAL):
            continue
        label = _site_label(d)
        similar = label == name or (len(label) >= 4 and len(name) >= 4 and (label in name or name in label))
        if (name and similar) or (first_word and len(first_word) >= 3 and label == first_word):
            scores[d] += 10 - min(rank, 9)
            # Look-alike and squatter domains ("razor-pay.com.in") lose to the plain name on a common TLD.
            if d.split(".")[0] in (name, first_word):
                scores[d] += 8
            if d.split(".", 1)[-1] in COMMON_TLDS:
                scores[d] += 6
            if "-" in d.split(".")[0]:
                scores[d] -= 4
    return scores.most_common(1)[0][0] if scores else None


def _results_block(results: list[SearchResult], limit: int = 20, chars: int = 300) -> str:
    lines = []
    for r in results[:limit]:
        when = r.published_at.date().isoformat() if r.published_at else ""
        lines.append(f"- {r.title} | {r.url}" + (f" | {when}" if when else "") +
                     f"\n  {truncate(' '.join((r.snippet or '').split()), chars)}")
    return "\n".join(lines)


def _dedupe(results: list[SearchResult]) -> list[SearchResult]:
    seen: set[str] = set()
    out = []
    for r in results:
        key = normalize_url(r.url)
        if key not in seen:
            seen.add(key)
            out.append(r)
    return out


def _parse_iso(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value.strip()[:10])
    except ValueError:
        return None


class _BriefRun:
    def __init__(self, inputs: BriefInput, *, llm, search, reader: PageReader, wayback, deadline: Deadline,
                 trace: Trace, today: date):
        self.inputs = inputs
        self.search = search
        self.reader = reader
        self.wayback = wayback
        self.deadline = deadline
        self.trace = trace
        self.models = _Models(llm, trace, deadline)
        self.today = today
        self.state = BriefState(company=Company(query=inputs.company, name=inputs.company))
        self.your_company = inputs.your_company
        self._page_text: dict[str, str] = {}
        self._page_doc_words: dict[str, int] = {}

    # ------------------------------------------------------------------ helpers

    def _requester(self) -> str:
        return self.your_company or "not described (write for a competitor in the same industry)"

    async def _search(self, query: str, **kw) -> list[SearchResult]:
        timeout = self.deadline.slice(20.0, reserve=IMPACT_RESERVE_S)
        if timeout < 3 * self.deadline.scale:
            return []
        try:
            return await asyncio.wait_for(self.search.search(query, **kw), timeout)
        except Exception as e:  # search failures shrink the brief, they never stop it
            log.warning("search %r failed: %s", query, e)
            self.state.warnings.append(f"Search '{query}' failed: {type(e).__name__}")
            return []

    # ------------------------------------------------------------------ stage 0: what to research

    async def normalize(self) -> None:
        if not looks_like_request(self.inputs.company):
            return
        async with self.trace.step("Understand the request", "fast model") as st:
            try:
                out = await self.models.call(
                    CompanyNameOut, step=st, tier="fast", system=prompts.COMPANY_NAME,
                    prompt=f"MESSAGE:\n{_fence(self.inputs.company)}", purpose="Extract company name", cap_s=30,
                    reserve_s=150, max_tokens=400,
                )
                if out.company.strip():
                    self.state.company.query = self.state.company.name = out.company.strip()[:200]
                if not self.your_company and out.your_company.strip():
                    self.your_company = out.your_company.strip()[:500]
                st.detail = f"company: {self.state.company.query}"
            except Exception as e:
                st.status = "partial"
                st.detail = f"used the text as given ({type(e).__name__})"

    # ------------------------------------------------------------------ stage 1-2: search + resolve

    async def research(self) -> tuple[list[SearchResult], list[SearchResult], list[SearchResult]]:
        q = self.state.company.query
        focus = self.inputs.focus
        async with self.trace.step("Search the web and news", "web search") as st:
            general, news_a, news_b, news_c = await asyncio.gather(
                self._search(f"{q} official website", max_results=8),
                self._search(q, topic="news", recency_days=NEWS_WINDOW_DAYS, max_results=12),
                self._search(f"{q} {NEWS_QUERY_BY_FOCUS[focus]}", topic="news", recency_days=NEWS_WINDOW_DAYS,
                             max_results=8),
                self._search(f"{q} announces", topic="news", recency_days=NEWS_WINDOW_DAYS, max_results=8),
            )
            st.tool_calls = 4
            news_found = _dedupe(news_a + news_b + news_c)
            st.detail = f"{len(general)} web results, {len(news_found)} news results"
        domain = guess_domain(q, general)
        site_pages: list[SearchResult] = []
        site_news: list[SearchResult] = []
        if domain:
            async with self.trace.step("Map the official site", "site search") as st:
                site_pages, site_news = await asyncio.gather(
                    self._search(f"{q} {SITE_QUERY_BY_FOCUS[focus]}", include_domains=[domain], max_results=10),
                    self._search(f"{q} press release announcement news", include_domains=[domain],
                                 recency_days=NEWS_WINDOW_DAYS, max_results=8),
                )
                st.tool_calls = 2
                st.detail = f"likely official domain {domain}: {len(site_pages) + len(site_news)} pages found"
        self.state.company.domain = domain
        news = _dedupe(news_found + site_news)
        return general + site_pages, site_news, news

    async def resolve(self, results: list[SearchResult]) -> None:
        company = self.state.company
        async with self.trace.step("Resolve company and choose pages", "reasoning model") as st:
            prompt = (
                f"COMPANY REQUESTED: {company.query}\nREQUESTER: {self._requester()}\nFOCUS: {self.inputs.focus} - "
                f"{prompts.FOCUS_GUIDE[self.inputs.focus]}\nPREFERRED PAGE TYPES: "
                f"{prompts.PAGE_KINDS_BY_FOCUS[self.inputs.focus]}\nLIKELY OFFICIAL DOMAIN (heuristic): "
                f"{company.domain or 'unknown'}\n\nSEARCH RESULTS:\n{_fence(_results_block(_dedupe(results), 22))}"
            )
            try:
                out = await self.models.call(
                    ResolveOut, step=st, tier="reasoning", system=prompts.RESOLVE, prompt=prompt,
                    purpose="Resolve company and choose official pages", cap_s=75, reserve_s=IMPACT_RESERVE_S + 30,
                    max_tokens=3000,
                )
            except Exception as e:
                st.status = "partial"
                st.detail = f"model unavailable ({type(e).__name__}); chose pages by URL heuristics"
                company.resolved_by = "heuristic"
                self._heuristic_pages(results)
                return
            guessed = company.domain
            domain = registrable_domain(out.official_domain) if out.official_domain else None
            if domain and not domain_matches(f"https://{domain}", NOT_OFFICIAL):
                company.domain = domain
            company.name = out.company_name.strip() or company.name
            company.description = out.description.strip()
            company.industry = out.industry.strip()
            company.ambiguity_note = out.ambiguity_note.strip()
            seen: set[str] = set()
            for pick in out.pages:
                url = pick.url.strip()
                if not url.startswith("http"):
                    url = "https://" + url.lstrip("/")
                if not company.domain or not domain_matches(url, [company.domain]):
                    continue
                key = normalize_url(url)
                if key in seen:
                    continue
                seen.add(key)
                self.state.pages.append(PageInfo(url=url, kind=pick.kind, reason=pick.reason.strip(),
                                                 watch=[w for w in pick.watch if w.strip()][:5]))
            # Individual blog posts and guides are marketing content, not the company's current terms.
            sections = [p for p in self.state.pages if not _is_article(p.url)]
            if len(sections) >= 2:
                self.state.pages = sections
            self.state.pages = self.state.pages[:MAX_PAGES]
            if company.domain and company.domain != guessed and len(self.state.pages) < 3:
                # The heuristic mapped the wrong site: map the domain the model identified.
                extra = await self._search(f"{company.name} {SITE_QUERY_BY_FOCUS[self.inputs.focus]}",
                                           include_domains=[company.domain], max_results=10)
                st.tool_calls += 1
                results = results + extra
            if len(self.state.pages) < 3:
                self._heuristic_pages(results)
            if company.domain and len(self.state.pages) < MAX_PAGES and not any(
                    _path(p.url) == "/" for p in self.state.pages):
                # Homepages are archived often and carry the company's headline claims.
                self.state.pages.append(PageInfo(url=f"https://{company.domain}/", kind="homepage",
                                                 reason="headline positioning; well archived"))
            st.detail = (f"{company.name} ({company.domain or 'domain unknown'}); "
                         f"{len(self.state.pages)} official pages chosen")

    def _heuristic_pages(self, results: list[SearchResult]) -> None:
        """Fallback page choice: URLs on the official domain, ranked by what they look like."""
        domain = self.state.company.domain
        if not domain:
            return
        keywords = [("pricing", "pricing"), ("fees", "pricing"), ("product", "products"), ("press", "newsroom"),
                    ("news", "newsroom"), ("blog", "newsroom"), ("terms", "legal"), ("policy", "legal"),
                    ("about", "about"), ("careers", "careers"), ("investor", "investors")]
        target = 3 if self.state.pages else 4  # top up the model's choice; replace it on failure
        have = {normalize_url(p.url) for p in self.state.pages}
        ranked: list[tuple[int, str, str]] = []
        for r in _dedupe(results):
            if not domain_matches(r.url, [domain]) or normalize_url(r.url) in have:
                continue
            path = r.url.lower()
            hit = next(((i, kind) for i, (kw, kind) in enumerate(keywords) if kw in path), (len(keywords), "other"))
            ranked.append((hit[0] + (100 if _is_article(r.url) else 0), r.url, hit[1]))
        if not any(p.kind == "homepage" for p in self.state.pages):
            ranked.append((len(keywords) + 1, f"https://{domain}/", "homepage"))
        for _rank, url, kind in sorted(ranked)[: max(0, target - len(self.state.pages))]:
            self.state.pages.append(PageInfo(url=url, kind=kind, reason="found on the official site by search"))
        if not self.state.company.description:
            top = next((r for r in results if domain_matches(r.url, [domain])), None)
            if top:
                self.state.company.description = truncate(" ".join(top.snippet.split()), 240)

    # ------------------------------------------------------------------ stage 3: read + extract + history

    def _history_candidates(self) -> list[PageInfo]:
        """Pages worth reconstructing, best first: stable section pages over blog posts and articles.

        One more than :data:`HISTORY_PAGES` is looked up, because the archive often has no
        usable capture of a given page in the window.
        """
        order = {k: i for i, k in enumerate(HISTORY_KIND_ORDER)}

        def rank(p: PageInfo) -> tuple[bool, bool, int, int]:
            path = _path(p.url).lower()
            article = any(seg in path for seg in ("/blog/", "/news/", "/press/", "/stories/", "/learn/"))
            kind = "homepage" if path == "/" else p.kind  # models label the homepage inconsistently
            # Pricing pages first (by URL, whatever the label): that is where changes hurt competitors.
            return article, "pric" not in path, order[kind], path.count("/") if path != "/" else 0

        eligible = [p for p in self.state.pages if p.kind in order]
        return sorted(eligible, key=rank)[: HISTORY_PAGES + 1]

    async def pages_and_history(self) -> None:
        if not self.state.pages:
            self.state.history_note = "No official pages were identified, so no history was reconstructed."
            return
        stage_end = IMPACT_RESERVE_S
        history_pages = self._history_candidates() if self.wayback is not None else []
        capture_tasks = {p.url: asyncio.ensure_future(self._find_capture(p.url)) for p in history_pages}

        async with self.trace.step("Read official pages", f"page reader ({self.reader.name})") as st:
            urls = [p.url for p in self.state.pages]
            st.tool_calls = len(urls)
            try:
                read = await asyncio.wait_for(self.reader.read_many(urls),
                                              max(1.0, self.deadline.slice(45, reserve=stage_end + 25)))
            except Exception as e:
                read = [ReadPage(u, u, None, "", False, f"{type(e).__name__}", "none") for u in urls]
            for page, rp in zip(self.state.pages, read, strict=False):
                page.final_url, page.ok, page.problem, page.via, page.words = (
                    rp.final_url, rp.ok, rp.reason, rp.via, rp.words)
                if rp.ok:
                    self._page_text[page.url] = rp.text
            ok = [p for p in self.state.pages if p.ok]
            vias = Counter(p.via for p in ok)
            st.detail = f"{len(ok)}/{len(urls)} pages readable" + (
                f" ({', '.join(f'{n} via {v}' for v, n in vias.items())})" if ok else "")
            if not ok:
                st.status = "partial"

        async with self.trace.step("Extract facts with verified quotes", "fast model + quote check") as st:
            ok_pages = [p for p in self.state.pages if p.ok]
            results = await _gather_limited(
                [self._extract(p, st) for p in ok_pages], self.deadline.slice(80, reserve=stage_end + 10))
            for p, res in zip(ok_pages, results, strict=False):
                if isinstance(res, BaseException):
                    p.problem = f"extraction failed: {type(res).__name__}"
                    st.status = "partial"
            st.detail = (f"{len(self.state.facts)} facts kept from {len(ok_pages)} pages; "
                         f"{self.state.dropped_quotes} unverifiable quotes dropped")

        if not history_pages:
            for t in capture_tasks.values():
                t.cancel()
            self.state.history_note = self.state.history_note or "Archive history was not requested for these pages."
            return
        async with self.trace.step(f"Compare with Wayback capture from ~{self.inputs.months_back} months ago",
                                   "Wayback Machine + fast model") as st:
            # The lookups ran while pages were read and extracted; give stragglers a little longer.
            wait_s = self.deadline.slice(45, reserve=stage_end + 30)
            await asyncio.wait(list(capture_tasks.values()), timeout=max(0.1, wait_s))
            chosen: list[PageInfo] = []
            notes: list[str] = []
            for p in history_pages:
                label = f"{host_of(p.url)}{_path(p.url)}"
                task = capture_tasks[p.url]
                if not task.done():
                    notes.append(f"{label}: archive lookup timed out")
                elif task.exception() is not None:
                    notes.append(f"{label}: archive lookup failed ({type(task.exception()).__name__})")
                elif isinstance(task.result(), str):
                    notes.append(f"{label}: {task.result()}")
                elif not p.ok:
                    notes.append(f"{label}: current page unreadable")
                elif len(chosen) < HISTORY_PAGES:
                    chosen.append(p)
            for t in capture_tasks.values():
                if not t.done():
                    t.cancel()
            outcomes = await _gather_limited(
                [self._history(p, capture_tasks[p.url], st) for p in chosen],
                self.deadline.slice(100, reserve=stage_end),
            )
            for p, res in zip(chosen, outcomes, strict=False):
                if isinstance(res, BaseException):
                    notes.append(f"{host_of(p.url)}{_path(p.url)}: {type(res).__name__ if not str(res) else res}")
                elif res:
                    notes.append(res)
            st.tool_calls = len(history_pages) + len(chosen)
            st.detail = (f"{len(self.state.changes)} verified changes across {len(chosen)} archived pages"
                         + (f"; {'; '.join(notes)}" if notes else ""))
            if not self.state.changes:
                st.status = "partial" if not chosen else "ok"
                self.state.history_note = (
                    "No verified change was found on the archived pages." if chosen and not notes
                    else "History: " + "; ".join(notes))

    async def _extract(self, page: PageInfo, st: Step) -> None:
        text = self._page_text[page.url]
        terms = [w for item in page.watch for w in item.split() if len(w) > 3]
        excerpt = window_around(text, terms, radius=900, max_chars=PAGE_CHARS) if len(text) > PAGE_CHARS else text
        prompt = (
            f"COMPANY: {self.state.company.name}\nFOCUS: {self.inputs.focus} - "
            f"{prompts.FOCUS_GUIDE[self.inputs.focus]}\nPAGE: {page.url} ({page.kind})\nWATCH: "
            f"{'; '.join(page.watch) or 'whatever matters most for the focus'}\n\nPAGE TEXT:\n{_fence(excerpt)}"
        )
        out = await self.models.call(ExtractOut, step=st, tier="fast", system=prompts.EXTRACT, prompt=prompt,
                                     purpose=f"Extract facts from {page.url}", cap_s=60, reserve_s=IMPACT_RESERVE_S,
                                     max_tokens=3000)
        page.summary = out.page_summary.strip()
        seen: set[str] = set()
        for f in out.facts[:8]:
            label = f.label.strip()
            if not label or not f.value.strip() or normalize_for_match(label) in seen:
                continue
            if not f.quote.strip() or not quote_in_text(f.quote, text) or not _numbers_supported(
                    f"{label} {f.value}", f.quote):
                self.state.dropped_quotes += 1  # unverifiable quote, or a number the quote does not show
                continue
            if any(normalize_for_match(f.quote) == normalize_for_match(x.quote) and
                   normalize_for_match(label) == normalize_for_match(x.label) for x in self.state.facts):
                continue
            seen.add(normalize_for_match(label))
            self.state.facts.append(Fact(id="", category=f.category, label=label, value=f.value.strip(),
                                         quote=f.quote.strip(), url=page.final_url or page.url, page_kind=page.kind))

    async def _find_capture(self, url: str) -> tuple[Any, ExtractedDoc] | str:
        """Closest usable archive capture to ``months_back`` ago, or a reason string."""
        months = self.inputs.months_back
        target = self.today - timedelta(days=round(30.44 * months))
        since = target - timedelta(days=75)
        until = min(self.today - timedelta(days=20), target + timedelta(days=75))
        problem = None
        try:
            captures = await asyncio.wait_for(
                self.wayback.list_captures(url, since=since, until=until, per="month", limit=8),
                max(1.0, 30 * self.deadline.scale))
        except Exception as e:  # CDX is often overloaded (503s); try the lighter availability API
            captures, problem = [], f"archive lookup failed ({type(e).__name__})"
        if not captures and hasattr(self.wayback, "closest_capture"):
            try:
                cap = await asyncio.wait_for(self.wayback.closest_capture(url, target),
                                             max(1.0, 20 * self.deadline.scale))
            except Exception:
                cap = None
            if cap is not None and since <= cap.captured_at.date() <= until:
                captures = [cap]
        if not captures:
            return problem or f"no archive capture between {since:%b %Y} and {until:%b %Y}"
        ranked = sorted(captures, key=lambda c: abs((c.captured_at.date() - target).days))
        problems = []
        for cap in ranked[:3]:
            fr = await self.wayback.fetch_capture(cap)
            doc = extract_result(fr, mode="page") if fr.ok else None
            if doc is not None and doc.quality == "ok":
                return cap, doc
            problems.append((doc.quality_reason if doc else (fr.error or f"HTTP {fr.status}")) or "unusable")
        return f"archive captures unusable ({'; '.join(problems[:2])})"

    async def _history(self, page: PageInfo, capture_task: asyncio.Future, st: Step) -> str | None:
        label = f"{host_of(page.url)}{_path(page.url)}"
        if not page.ok:
            return f"{label}: current page unreadable"
        found = await capture_task
        if isinstance(found, str):
            return f"{label}: {found}"
        cap, old_doc = found
        page_facts = [f for f in self.state.facts if f.url == (page.final_url or page.url)]
        current = self._page_text[page.url]
        terms = [w for f in page_facts for w in (f.label + " " + f.value).split() if len(w) > 3] + \
                [w for item in page.watch for w in item.split() if len(w) > 3]
        old_text = old_doc.text
        old_excerpt = window_around(old_text, terms, radius=700, max_chars=HISTORY_CHARS) \
            if len(old_text) > HISTORY_CHARS else old_text
        new_excerpt = window_around(current, terms, radius=700, max_chars=HISTORY_CHARS) \
            if len(current) > HISTORY_CHARS else current
        facts_block = "\n".join(f"[{i}] {f.label}: {f.value}" for i, f in enumerate(page_facts)) or "(none extracted)"
        captured = cap.captured_at.date()
        prompt = (
            f"COMPANY: {self.state.company.name}\nPAGE: {page.url}\nFOCUS: {self.inputs.focus}\n"
            f"ARCHIVED CAPTURE DATE: {captured.isoformat()}\nTODAY: {self.today.isoformat()}\n\n"
            f"CURRENT FACTS:\n{facts_block}\n\nARCHIVED TEXT ({captured.isoformat()}):\n{_fence(old_excerpt)}\n\n"
            f"CURRENT TEXT ({self.today.isoformat()}):\n{_fence(new_excerpt)}"
        )
        out = await self.models.call(HistoryOut, step=st, tier="fast", system=prompts.HISTORY, prompt=prompt,
                                     purpose=f"Compare {label} with {captured.isoformat()} capture", cap_s=75,
                                     reserve_s=IMPACT_RESERVE_S - 10, max_tokens=3000)
        comparable = old_doc.word_count >= 0.5 * max(1, page.words)
        before_count = len(self.state.changes)
        for item in out.facts:
            if not 0 <= item.id < len(page_facts):
                continue
            fact = page_facts[item.id]
            if not item.present:
                # Absence is only meaningful when the archived page is of comparable size.
                if comparable and not quote_in_text(fact.quote, old_text):
                    self._add_change("added", fact.category, fact.label, "Not on the page", fact.value, "",
                                     fact.quote, page, cap, captured)
                continue
            if not item.quote.strip() or not quote_in_text(item.quote, old_text) or not _numbers_supported(
                    item.value, item.quote):
                self.state.dropped_quotes += 1
                continue
            if not _values_differ(item.value, fact.value, item.quote, fact.quote):
                continue
            if quote_in_text(item.quote, current):  # the old statement is still on the page
                continue
            self._add_change("changed", fact.category, fact.label, item.value.strip(), fact.value, item.quote.strip(),
                             fact.quote, page, cap, captured)
        for oc in out.other_changes[:3]:
            before_ok = bool(oc.before_quote.strip()) and quote_in_text(oc.before_quote, old_text)
            after_ok = bool(oc.after_quote.strip()) and quote_in_text(oc.after_quote, current)
            if not oc.before_quote.strip() and after_ok:
                # Something new on the page ("Free payment gateway for first 90 days"): only
                # credible when the archived page is comparable and really lacks the statement.
                if comparable and not quote_in_text(oc.after_quote, old_text):
                    title = oc.title.strip() or truncate(oc.after_quote.strip(), 60)
                    self._add_change("added", oc.category, title, "Not on the page", oc.after_quote.strip(), "",
                                     oc.after_quote.strip(), page, cap, captured)
                continue
            if not (before_ok and after_ok):
                self.state.dropped_quotes += 1
                continue
            if quote_in_text(oc.before_quote, current) or quote_in_text(oc.after_quote, old_text):
                continue  # both statements exist on both versions: not a change
            if not _substantively_different(oc.before_quote, oc.after_quote):
                continue  # formatting, markup or punctuation only
            if fuzz.token_sort_ratio(normalize_for_match(oc.before_quote), normalize_for_match(oc.after_quote)) < 55:
                continue  # two unrelated statements paired up: not a before/after of one thing
            title = oc.title.strip() or truncate(oc.after_quote.strip(), 60)
            self._add_change("other", oc.category, title, oc.before_quote.strip(), oc.after_quote.strip(),
                             oc.before_quote.strip(), oc.after_quote.strip(), page, cap, captured)
        added = len(self.state.changes) - before_count
        return None if added else f"{label}: no material change since {captured:%d %b %Y}"

    def _add_change(self, kind: str, category: str, label: str, before: str, after: str, before_quote: str,
                    after_quote: str, page: PageInfo, cap, captured: date) -> None:
        key, quote_key = normalize_for_match(label), normalize_for_match(after_quote)
        if any(c.url == (page.final_url or page.url) and (
                normalize_for_match(c.label) == key or normalize_for_match(c.after_quote) == quote_key)
               for c in self.state.changes):
            return  # the same change reported twice (as a fact and as an "other" change)
        self.state.changes.append(Change(
            id="", kind=kind, category=category, label=label, before=truncate(before, 220),
            after=truncate(after, 220), before_quote=before_quote, after_quote=after_quote,
            url=page.final_url or page.url, archive_url=cap.archive_url, captured_on=captured,
            # Both sides are quotes verified on the company's own page (today and in the archive).
            status="confirmed",
        ))

    # ------------------------------------------------------------------ stage 4: news

    async def triage(self, news: list[SearchResult]) -> TriageOut | None:
        cutoff = datetime.now(UTC) - timedelta(days=NEWS_WINDOW_DAYS)
        items = [r for r in news if r.published_at is None or r.published_at >= cutoff]
        items.sort(key=lambda r: (r.published_at is None, -(r.published_at.timestamp() if r.published_at else 0)))
        items = items[:20]
        self._news_items = items
        self.state.news_screened = len(items)
        if not items:
            return None
        lines = []
        for i, r in enumerate(items):
            when = r.published_at.date().isoformat() if r.published_at else "unknown date"
            body = " ".join(((r.content or r.snippet) or "").split())[:700]
            lines.append(f"[{i}] {r.title}\n    publisher: {r.publisher} | date: {when} | url: {r.url}\n    {body}")
        prompt = (
            f"TODAY: {self.today.isoformat()}. WINDOW: last {NEWS_WINDOW_DAYS} days.\nCOMPANY: "
            f"{self.state.company.name} ({self.state.company.domain or 'domain unknown'})"
            + (f" - {self.state.company.description}" if self.state.company.description else "")
            + f"\nREQUESTER: {self._requester()}\nFOCUS: {self.inputs.focus} - {prompts.FOCUS_GUIDE[self.inputs.focus]}"
            f"\n\nITEMS:\n{_fence(chr(10).join(lines))}\n\nReturn one entry per item id."
        )
        async with self.trace.step("Triage recent news", "fast model") as st:
            st.detail = f"{len(items)} items screened"
            try:
                out = await self.models.call(TriageOut, step=st, tier="fast", system=prompts.TRIAGE, prompt=prompt,
                                             purpose=f"Triage {len(items)} news items", cap_s=90,
                                             reserve_s=IMPACT_RESERVE_S - 15, max_tokens=5000)
            except Exception as e:
                st.status = "partial"
                st.detail += f"; triage unavailable ({type(e).__name__})"
                return None
            st.detail += f"; {sum(1 for i in out.items if i.relevant)} relevant"
            return out

    async def verify_news(self, triage: TriageOut | None) -> None:
        items = getattr(self, "_news_items", [])
        if triage is None:
            self._untriaged_news(items)
            return
        domain = self.state.company.domain
        async with self.trace.step("Cluster stories and compute evidence status", "code (evidence rules)") as st:
            stories: dict[int, list[tuple[Any, SearchResult]]] = {}
            for t in triage.items:
                if not t.relevant or t.materiality == "none" or not 0 <= t.id < len(items):
                    continue
                when = _parse_iso(t.occurred_at)
                if when and when < self.today - timedelta(days=NEWS_WINDOW_DAYS + 7):
                    continue  # old news resurfacing
                stories.setdefault(t.story if t.story > 0 else 1000 + t.id, []).append((t, items[t.id]))
            stories = _merge_similar_stories(stories, self.state.company.name)
            built: list[Story] = []
            for members in stories.values():
                sources: list[Source] = []
                evidence: list[EvidenceItem] = []
                for t, r in members:
                    text = f"{r.title}\n{r.snippet}\n{r.content or ''}"
                    verified = bool(t.quote.strip()) and quote_in_text(t.quote, text)
                    if t.quote.strip() and not verified:
                        self.state.dropped_quotes += 1
                    cls = classify_source(r.url, entity_domains=[domain] if domain else [])
                    sources.append(Source(publisher=r.publisher, url=r.url, title=r.title,
                                          quote=t.quote.strip() if verified else "", quote_verified=verified,
                                          source_class=cls,
                                          published=r.published_at.date() if r.published_at else None))
                    evidence.append(EvidenceItem(source_class=cls, stance="supports", publisher=r.publisher,
                                                 quote=t.quote, quote_verified=verified, url=r.url))
                verdict = assess(evidence)
                lead = max(members, key=lambda m: _MATERIALITY_RANK[m[0].materiality])[0]
                dates = [d for d in ([_parse_iso(t.occurred_at) for t, _ in members] +
                                     [s.published for s in sources]) if d]
                sources.sort(key=lambda s: (s.source_class != "primary", not s.quote_verified))
                built.append(Story(id="", headline=lead.headline.strip() or members[0][1].title, claim=lead.claim.strip(),
                                   event_type=lead.event_type, materiality=lead.materiality,
                                   when=min(dates) if dates else None, status=verdict.status,
                                   status_summary=verdict.summary, sources=sources))
            built.sort(key=lambda s: (-_MATERIALITY_RANK[s.materiality], -_STATUS_RANK[s.status],
                                      -(s.when.toordinal() if s.when else 0)))
            self.state.stories = built[:6]
            counts = Counter(STATUS_LABELS[s.status] for s in self.state.stories)
            st.detail = (f"{len(built)} stories; kept {len(self.state.stories)}: "
                         + (", ".join(f"{n} {k.lower()}" for k, n in counts.items()) or "none"))

    def _untriaged_news(self, items: list[SearchResult]) -> None:
        """Without triage, still list the newest dated headlines - clearly marked as not assessed."""
        dated = [r for r in items if r.published_at is not None and not domain_matches(r.url, NOT_OFFICIAL[:20])]
        for r in dated[:4]:
            cls = classify_source(r.url, entity_domains=[self.state.company.domain] if self.state.company.domain else [])
            self.state.stories.append(Story(
                id="", headline=r.title, claim="", event_type="other", materiality="low", when=r.published_at.date(),
                status="unverified", status_summary="Not triaged or verified (model unavailable).",
                sources=[Source(publisher=r.publisher, url=r.url, title=r.title, quote="", quote_verified=False,
                                source_class=cls, published=r.published_at.date())]))
        if self.state.stories:
            self.state.warnings.append("News could not be triaged in time; recent headlines are listed unverified.")

    # ------------------------------------------------------------------ stage 5: impact

    def _number_ids(self) -> None:
        for i, f in enumerate(self.state.facts, 1):
            f.id = f"S{i}"
        for i, c in enumerate(self.state.changes, 1):
            c.id = f"C{i}"
        for i, s in enumerate(self.state.stories, 1):
            s.id = f"N{i}"

    async def impact(self) -> None:
        self._number_ids()
        s = self.state
        company = s.company
        facts = "\n".join(f"[{f.id}] ({f.category}) {f.label}: {f.value} - quote: \"{truncate(f.quote, 160)}\""
                          for f in s.facts[:24]) or "(none)"
        changes = "\n".join(
            f"[{c.id}] {c.label}: before ({c.captured_on.isoformat()}): {c.before} -> now: {c.after} "
            f"[{STATUS_LABELS[c.status]}]" for c in s.changes) or "(none found)"
        news = "\n".join(
            f"[{n.id}] {n.when.isoformat() if n.when else 'date unknown'} | {n.headline} | claim: {n.claim} | "
            f"evidence: {STATUS_LABELS[n.status]} ({len(n.sources)} source(s))" for n in s.stories) or "(none)"
        prompt = (
            f"TODAY: {self.today.isoformat()}\nREQUESTER (the reader): {self._requester()}\n"
            f"SUBJECT: {company.name} ({company.domain or 'domain unknown'}) - {company.description or 'n/a'}"
            f" Industry: {company.industry or 'n/a'}\nFOCUS: {self.inputs.focus}\n"
            f"LANGUAGE: {prompts.LANGUAGE_RULE[self.inputs.language]}\n\n"
            f"VERIFIED CURRENT FACTS (official pages):\n{_fence(facts)}\n\n"
            f"VERIFIED CHANGES vs ~{self.inputs.months_back} months ago (Wayback Machine):\n{_fence(changes)}\n\n"
            f"RECENT DEVELOPMENTS (last {NEWS_WINDOW_DAYS} days):\n{_fence(news)}"
        )
        async with self.trace.step("Assess impact and recommend actions", "reasoning model") as st:
            if not (s.facts or s.changes or s.stories):
                st.status = "skipped"
                st.detail = "nothing verified to assess"
                return
            try:
                out = await self.models.call(ImpactOut, step=st, tier="reasoning",
                                             system=prompts.IMPACT + "\n" + prompts.LANGUAGE_RULE[self.inputs.language],
                                             prompt=prompt, purpose="Impact analysis", cap_s=110, reserve_s=4,
                                             max_tokens=5000)
            except Exception as e:
                st.status = "partial"
                st.detail = f"impact analysis unavailable ({type(e).__name__}); facts shown without assessment"
                s.warnings.append("The impact analysis did not finish in time; the brief shows verified facts only.")
                return
            valid = {f.id for f in s.facts} | {c.id for c in s.changes} | {n.id for n in s.stories}
            cited = []
            for f in out.facts:
                refs = [r.strip().strip("[]") for r in f.refs if r.strip().strip("[]") in valid]
                if refs and f.statement.strip():  # a "fact" with no valid citation is not a fact
                    cited.append({"statement": f.statement.strip(), "refs": refs})
            s.impact = {
                "executive_summary": out.executive_summary.strip(),
                "facts": cited[:6],
                "assessment": [a.strip() for a in out.assessment if a.strip()][:4],
                "actions": [a.model_dump() for a in out.actions if a.action.strip()][:3],
                "watch_next": [w.strip() for w in out.watch_next if w.strip()][:3],
                "assumptions": [a.strip() for a in out.assumptions if a.strip()][:3],
            }
            notes = {n.id.strip(): n.text.strip() for n in out.change_notes if n.text.strip()}
            for c in s.changes:
                c.note = notes.get(c.id, "")
            heads = {n.id.strip(): n.text.strip() for n in out.headlines if n.text.strip()}
            for n in s.stories:
                if heads.get(n.id):
                    n.headline = heads[n.id]
            st.detail = (f"{len(s.impact['facts'])} cited facts, {len(s.impact['assessment'])} assessment points, "
                         f"{len(s.impact['actions'])} actions")


def _merge_similar_stories(stories: dict[int, list], company: str = "") -> dict[int, list]:
    """Merge story groups the model split but that report one event (same type, near-identical headline).

    Fifteen articles about one IPO filing should be one development with fifteen sources;
    models sometimes number "files for $600M IPO" and "files for $500M IPO" separately.
    """
    keys = list(stories)
    parent = {k: k for k in keys}

    def find(k: int) -> int:
        while parent[k] != k:
            k = parent[k]
        return k

    own = {w.lower() for w in re.findall(r"\w+", company)}

    def head(k: int) -> tuple[str, str, set[str]]:
        t = stories[k][0][0]
        raw = t.headline or stories[k][0][1].title
        names = {w.lower() for w in re.findall(r"\b[A-Z][A-Za-z0-9]{3,}\b", raw)} - own - _GENERIC_CAPS
        return t.event_type, normalize_for_match(raw), names

    for i, a in enumerate(keys):
        for b in keys[i + 1:]:
            (ta, ha, na), (tb, hb, nb) = head(a), head(b)
            if not (ha and hb):
                continue
            ratio = fuzz.token_set_ratio(ha, hb)
            # Same event type and near-identical headline, or a shared distinctive name ("Vulcan").
            if (ta == tb and ratio >= STORY_MERGE_SIMILARITY) or (na & nb and ratio >= 55):
                parent[find(b)] = find(a)
    merged: dict[int, list] = {}
    for k in keys:
        merged.setdefault(find(k), []).extend(stories[k])
    return merged


_GENERIC_CAPS = {"india", "indian", "first", "launches", "launch", "announces", "files", "report", "reports",
                 "says", "partners", "with", "from", "after", "over", "into", "new"}
_MATERIALITY_RANK = {"none": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}
_STATUS_RANK = {"unverified": 0, "single_source": 1, "conflicting": 1, "corroborated": 2, "confirmed": 3}


def _path(url: str) -> str:
    m = re.match(r"^[a-z]+://[^/]+(/[^?#]*)?", url, re.I)
    path = (m.group(1) if m else "") or "/"
    return path.rstrip("/") or "/"


_ARTICLE_SEGMENTS = ("/blog/", "/blogs/", "/learn/", "/guides/", "/resources/", "/stories/", "/articles/")


def _is_article(url: str) -> bool:
    path = _path(url).lower() + "/"
    return any(seg in path and path.split(seg, 1)[1].strip("/") for seg in _ARTICLE_SEGMENTS)


_INDIAN_UNITS = re.compile(r"(\d+(?:\.\d+)?)\s*(lakhs?|lacs?|crores?|cr)\b", re.I)


def _expand_units(text: str) -> str:
    """'₹5 Lakh' and '₹5,00,000' are the same amount; compare them as one number."""
    def repl(m: re.Match[str]) -> str:
        factor = 10_000_000 if m.group(2).lower().startswith("cr") else 100_000
        return str(round(float(m.group(1)) * factor))
    return _INDIAN_UNITS.sub(repl, text)


def _numbers_supported(claim: str, quote: str) -> bool:
    """Every number in a model's value must be visible in its verified quote (no computed or
    remembered figures): "2.36% effective" is rejected when the quote only says "2% + 18% GST"."""
    wanted = _numbers(_expand_units(claim))
    shown = _numbers(quote) | _numbers(_expand_units(quote))
    return wanted <= shown


def _words(text: str) -> str:
    return " ".join(re.findall(r"\w+", normalize_for_match(_expand_units(text).replace(",", ""))))


def _substantively_different(before: str, after: str) -> bool:
    """False when two statements differ only in markup, punctuation, spacing or word order."""
    a, b = _words(before), _words(after)
    if a == b or (_numbers(_expand_units(before)) == _numbers(_expand_units(after))
                  and fuzz.token_set_ratio(a, b) >= 95):
        return False
    return True


def _values_differ(old_value: str, new_value: str, old_quote: str, new_quote: str) -> bool:
    """Deterministic before/after comparison (models only read values; code decides "changed")."""
    if normalize_for_match(old_quote) == normalize_for_match(new_quote):
        return False
    old_n, new_n = _numbers(old_value), _numbers(new_value)
    if old_n or new_n:
        return old_n != new_n
    if not _substantively_different(old_value, new_value):
        return False
    a, b = normalize_for_match(old_value), normalize_for_match(new_value)
    return a != b and fuzz.token_set_ratio(a, b) < 80


async def run_brief(
    inputs: BriefInput,
    *,
    llm,
    search,
    fetcher=None,
    reader: PageReader | None = None,
    wayback=None,
    deadline_s: float = 240.0,
    on_step: StepCallback | None = None,
    app_url: str | None = None,
    today: date | None = None,
) -> BriefResult:
    """Research ``inputs.company`` and return a rendered brief. Never raises for research failures."""
    deadline = Deadline(deadline_s)
    trace = Trace(deadline=deadline, on_step=on_step)
    if reader is None:
        reader = make_reader(reader_mode(), fetcher=fetcher, tavily=search)
    today = today or datetime.now(UTC).date()
    run = _BriefRun(inputs, llm=llm, search=search, reader=reader, wayback=wayback, deadline=deadline, trace=trace,
                    today=today)
    try:
        await run.normalize()
        results, _site_news, news = await run.research()
        triage_task = asyncio.ensure_future(run.triage(news))
        await run.resolve(results)
        await run.pages_and_history()
        try:
            triage = await asyncio.wait_for(triage_task, max(1.0, deadline.slice(60, reserve=IMPACT_RESERVE_S - 20)))
        except Exception as e:
            triage = None
            run.state.warnings.append(f"News triage did not finish ({type(e).__name__}).")
        await run.verify_news(triage)
        await run.impact()
    except Exception as e:  # last resort: render whatever was gathered
        log.exception("brief run failed")
        run.state.warnings.append(f"The run stopped early ({type(e).__name__}: {str(e)[:200]}).")
        run._number_ids()
    trace_list = trace.as_list()
    stats = {
        "seconds": round(deadline.elapsed, 1),
        "model_calls": trace.model_calls,
        "input_tokens": trace.input_tokens,
        "output_tokens": trace.output_tokens,
        "reader": reader.name,
        "model": getattr(llm, "reasoning_model", None),
    }
    markdown = render_markdown(run.state, inputs, trace_list, stats, today=today, app_url=app_url,
                               your_company=run.your_company, news_days=NEWS_WINDOW_DAYS)
    data = run.state.as_data()
    data.update({"input": inputs.model_dump(), "stats": stats, "your_company": run.your_company})
    return BriefResult(markdown=markdown, data=data, trace=trace_list)
