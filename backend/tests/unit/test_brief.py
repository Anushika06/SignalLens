"""The one-shot brief agent: pipeline, verification rules, degradation, readers and inputs."""

from __future__ import annotations

import pytest

from signallens.brief import BriefInput, BriefRequestError, parse_brief_request, run_brief
from signallens.brief.agent import _values_differ, guess_domain, looks_like_request
from signallens.brief.reader import AutoReader, DirectReader, TavilyReader, clean_markdown, make_reader
from signallens.fetch.http import FetchResult
from signallens.search.base import SearchResult
from signallens.search.tavily import ExtractedContent
from tests.brief_scenario import (
    DOMAIN,
    NEWSROOM,
    PAGES,
    PRICING,
    BriefBrain,
    make_world,
)
from tests.integration.fakes import FakeFetcher

APP = "https://app.signallens.example"


async def _run(world, **kw):
    inputs = kw.pop("inputs", None) or BriefInput(company="Nimbus Pay", your_company="Orbit Payments — SMB gateway")
    return await run_brief(inputs, llm=world["llm"], search=world["search"], reader=DirectReader(world["fetcher"]),
                           wayback=world["wayback"], deadline_s=kw.pop("deadline_s", 60), app_url=APP, **kw)


# --------------------------------------------------------------------------- full run


async def test_brief_end_to_end_with_verified_history_and_news():
    world = make_world()
    steps = []
    result = await _run(world, on_step=steps.append)
    md, data = result.markdown, result.data

    # Resolution: official domain and on-domain pages only (the off-domain pick is dropped).
    assert data["company"]["domain"] == DOMAIN
    urls = [p["url"] for p in data["pages"]]
    assert urls[:2] == [PRICING, NEWSROOM] and all(DOMAIN in u for u in urls)
    assert len(urls) == 4 and urls[-1] == f"https://{DOMAIN}/"  # topped up by URL heuristics + homepage

    # Snapshot: the hallucinated quote never reaches the brief.
    labels = [f["label"] for f in data["facts"]]
    assert "Standard domestic fee" in labels and "Invented fee" not in labels
    assert data["unverified_quotes_dropped"] >= 2  # invented fee + made-up archive change

    # History: before -> after computed by code, both quotes verified.
    change = next(c for c in data["changes"] if c["label"] == "Standard domestic fee")
    assert (change["before"], change["after"], change["status"]) == ("2% per transaction", "2.5% per transaction",
                                                                     "confirmed")
    assert change["archive_url"].startswith("https://web.archive.org/web/")
    assert any(c["kind"] == "added" and c["label"] == "Introductory offer" for c in data["changes"])
    assert not any(c["label"] in ("Made-up change", "Unrelated pairing", "Promo launched") for c in data["changes"])
    assert len(data["changes"]) == 2  # the promo is reported once (as the fact), not again as an "other" change

    # News: official press release + two outlets -> Confirmed; the cricket story is gone.
    assert len(data["developments"]) == 1
    story = data["developments"][0]
    assert story["status"] == "confirmed"
    assert {s["source_class"] for s in story["sources"]} >= {"primary", "independent"}

    # Impact: uncited "facts" are dropped; actions are owned.
    assert [f["refs"] for f in data["impact"]["facts"]] == [["C1", "S1"]]
    assert [a["owner"] for a in data["impact"]["actions"]] == ["Sales", "Product", "Strategy"]

    for section in ("# Nimbus Pay — intelligence brief", "## What changed in the last 12 months",
                    "## Recent developments", "## Current snapshot", "## Why it matters to Orbit Payments",
                    "## Recommended actions", "## How the agent worked", "**Confirmed**"):
        assert section in md
    assert "| C1 | **Standard domestic fee** | 2% per transaction | 2.5% per transaction |" in md
    assert md.rstrip().endswith(f"SignalLens web app at {APP}_")
    assert "Invented fee" not in md

    # Trace: every step reported (also through on_step), model calls bounded.
    names = [s["name"] for s in result.trace]
    assert names[0] == "Search the web and news" and "Assess impact and recommend actions" in names
    assert len(steps) == len(result.trace)
    assert sum(world["brain"].calls.values()) == 7  # resolve, triage, 3 extractions (press page 404s), history, impact
    assert data["stats"]["model_calls"] == 7


async def test_free_text_request_is_resolved_to_a_company_first():
    world = make_world()
    result = await _run(world, inputs=BriefInput(company="What has Nimbus Pay been up to lately?"))
    assert world["brain"].calls["CompanyNameOut"] == 1
    assert result.data["company"]["query"] == "Nimbus Pay"
    assert "## Why it matters" in result.markdown


async def test_hindi_brief_asks_for_hindi_narrative_and_localises_headings():
    world = make_world()
    result = await _run(world, inputs=BriefInput(company="Nimbus Pay", language="hindi"))
    assert "Hindi" in world["brain"].systems["ImpactOut"][0]
    assert "## पिछले 12 महीनों में क्या बदला" in result.markdown
    assert "“Standard plan: 2.5% per successful transaction”" in result.markdown  # quotes stay verbatim


async def test_model_outage_still_returns_a_useful_brief():
    world = make_world(BriefBrain(fail={"*"}))
    result = await _run(world)
    md = result.markdown
    assert result.data["company"]["resolved_by"] == "heuristic"
    assert result.data["company"]["domain"] == DOMAIN
    assert any(p["url"] == PRICING for p in result.data["pages"])  # chosen by URL heuristics
    assert "impact analysis could not be completed" in md
    assert "SignalLens web app" in md
    assert any(s["status"] in ("partial", "failed") for s in result.trace)


async def test_tiny_deadline_degrades_without_raising():
    world = make_world()
    result = await _run(world, deadline_s=0.5)
    assert result.markdown.startswith("# ")
    assert "## How the agent worked" in result.markdown


async def test_search_failure_is_survived():
    from signallens.search.base import SearchError
    from signallens.search.fake import StaticSearch

    world = make_world()
    world["search"] = StaticSearch({"default": SearchError("down", retryable=True)})
    result = await _run(world)
    assert "## Recent developments" in result.markdown
    assert any("failed" in w for w in result.data["warnings"])


# --------------------------------------------------------------------------- deterministic rules


@pytest.mark.parametrize(("old", "new", "oq", "nq", "differ"), [
    ("2% per transaction", "2.5% per transaction", "a", "b", True),
    ("2% per txn", "2 % per transaction", "a", "b", False),
    ("Same", "Different", "same quote", "Same Quote", False),
    ("UPI, cards and wallets", "UPI, cards, wallets", "a", "b", False),
    ("Payment links", "Payment pages and invoices", "a", "b", True),
])
def test_values_differ(old, new, oq, nq, differ):
    assert _values_differ(old, new, oq, nq) is differ


def test_guess_domain_prefers_the_company_site_over_directories():
    results = [SearchResult(url="https://en.wikipedia.org/wiki/Razorpay", title="", snippet=""),
               SearchResult(url="https://www.linkedin.com/company/razorpay", title="", snippet=""),
               SearchResult(url="https://razorpay.com/", title="", snippet="")]
    assert guess_domain("Razorpay", results) == "razorpay.com"
    assert guess_domain("https://www.cashfree.com/pricing", []) == "cashfree.com"
    assert guess_domain("Unknown Co", results) is None
    # A short generic label ("pay") must not match "Razorpay".
    assert guess_domain("Razorpay", [SearchResult(url="https://pay.google.com/", title="", snippet="")]) is None


@pytest.mark.parametrize(("text", "free"), [
    ("Razorpay", False), ("razorpay.com", False), ("Tata Motors Limited", False),
    ("What is Razorpay up to?", True), ("tell me about the latest moves of PhonePe in payments", True),
])
def test_looks_like_request(text, free):
    assert looks_like_request(text) is free


# --------------------------------------------------------------------------- inputs


@pytest.mark.parametrize("body", [
    {"company": "Razorpay"},
    {"input": {"company": "Razorpay"}},
    {"inputs": {"company": "Razorpay", "focus": "pricing"}},
    {"query": "Razorpay"},
    {"message": "Razorpay"},
    {"prompt": "Razorpay"},
    {"topic": "Razorpay"},
    "Razorpay",
])
def test_parse_brief_request_accepts_lenient_shapes(body):
    assert parse_brief_request(body).company == "Razorpay"


def test_parse_brief_request_normalises_values():
    parsed = parse_brief_request({"inputs": {"company": "  Razorpay ", "your_company": "  ", "focus": "regulation",
                                             "language": "hi", "months_back": "18"}})
    assert parsed.company == "Razorpay" and parsed.your_company is None
    assert (parsed.focus, parsed.language, parsed.months_back) == ("Regulatory & compliance", "Hindi", 18)
    assert parse_brief_request({"company": "X", "months_back": 99}).months_back == 36
    assert parse_brief_request({"company": "X", "focus": "nonsense"}).focus == "Everything"
    assert parse_brief_request({"company": "X", "for": "Cashfree"}).your_company == "Cashfree"


@pytest.mark.parametrize("body", [{}, {"focus": "Everything"}, [], 42, {"company": "   "}])
def test_parse_brief_request_rejects_missing_company(body):
    with pytest.raises(BriefRequestError):
        parse_brief_request(body)


# --------------------------------------------------------------------------- readers


class FakeTavily:
    def __init__(self, pages: dict[str, str]):
        self.pages = pages
        self.calls: list[list[str]] = []

    async def extract(self, urls):
        self.calls.append(list(urls))
        return [ExtractedContent(u, self.pages.get(u, ""), None if u in self.pages else "failed") for u in urls]


class DownFetcher(FakeFetcher):
    async def fetch(self, url, **kw):
        self.calls.append(url)
        return FetchResult(url=url, final_url=url, status=None, content_type=None, content=b"", text=None, etag=None,
                           last_modified=None, not_modified=False, elapsed_ms=1, error="dns resolution failed")


TAVILY_TEXT = "## Pricing\n\n**Standard plan:** 2.5% per successful transaction. [Sign up](https://x.example)\n\n" + \
    " ".join(["Nimbus Pay helps Indian businesses accept payments."] * 6)


async def test_auto_reader_falls_back_to_tavily_and_then_stays_there():
    tavily = FakeTavily({PRICING: TAVILY_TEXT, NEWSROOM: TAVILY_TEXT})
    fetcher = DownFetcher()
    reader = make_reader("auto", fetcher=fetcher, tavily=tavily)
    assert isinstance(reader, AutoReader)
    first = await reader.read_many([PRICING])
    assert first[0].ok and first[0].via == "tavily"
    assert "Standard plan: 2.5% per successful transaction." in first[0].text  # markdown stripped
    assert reader.egress_restricted
    await reader.read_many([NEWSROOM])
    assert fetcher.calls == [PRICING]  # second batch went straight to Tavily
    assert tavily.calls == [[PRICING], [NEWSROOM]]


async def test_auto_reader_uses_direct_pages_when_they_work():
    tavily = FakeTavily({})
    reader = make_reader("auto", fetcher=FakeFetcher(PAGES), tavily=tavily)
    pages = await reader.read_many([PRICING])
    assert pages[0].ok and pages[0].via == "direct" and tavily.calls == []


def test_make_reader_modes():
    fetcher, tavily = FakeFetcher(), FakeTavily({})
    assert isinstance(make_reader("tavily", fetcher=fetcher, tavily=tavily), TavilyReader)
    assert isinstance(make_reader("direct", fetcher=fetcher, tavily=tavily), DirectReader)
    assert isinstance(make_reader("tavily", fetcher=fetcher, tavily=None), DirectReader)  # no Tavily: degrade


def test_reader_mode_env(monkeypatch):
    from signallens.brief.reader import reader_mode

    monkeypatch.setenv("SL_BRIEF_READER", "TAVILY")
    assert reader_mode() == "tavily"
    monkeypatch.setenv("SL_BRIEF_READER", "weird")
    assert reader_mode() == "auto"


def test_clean_markdown():
    assert clean_markdown("# Title\n\n**Bold** [link](https://x) ![img](y.png)\n|---|---|") == "Title\nBold link"


def test_markup_only_differences_are_not_changes():
    from signallens.brief.agent import _is_article, _substantively_different

    assert not _substantively_different("Terms: 1. Demat account", "Terms: 1. ##### 1. Demat account")
    assert not _substantively_different("No setup fee, no AMC.", "No setup fee — no AMC")
    assert _substantively_different("Plans start at ₹2499", "Plans start at ₹3499")
    assert _is_article("https://razorpay.com/blog/pricing-explained") and not _is_article("https://razorpay.com/blog/")
    assert not _is_article("https://razorpay.com/pricing/")
    assert clean_markdown("Terms: 1. ##### 1. Demat account") == "Terms: 1. 1. Demat account"


def test_lakh_and_crore_amounts_compare_as_numbers():
    from signallens.brief.agent import _substantively_different

    assert not _substantively_different("revenue more than ₹5Lakh?", "revenue more than ₹5,00,000?")
    assert not _substantively_different("₹2 crore", "₹2,00,00,000")
    assert _substantively_different("revenue more than ₹5Lakh?", "revenue more than ₹10,00,000?")


def test_split_reports_of_one_event_are_merged():
    from types import SimpleNamespace as NS

    from signallens.brief.agent import _merge_similar_stories

    def item(headline, event_type="funding"):
        return (NS(headline=headline, event_type=event_type), NS(title=headline))

    merged = _merge_similar_stories({
        1: [item("Razorpay confidentially files for $600 million IPO per Reuters")],
        2: [item("Razorpay confidentially files for $500 million IPO with SEBI per Bloomberg")],
        3: [item("Razorpay announces Vulcan AI payments model", "product_launch")],
    })
    assert sorted(len(v) for v in merged.values()) == [1, 2]


def test_stories_sharing_a_distinctive_name_are_merged():
    from types import SimpleNamespace as NS

    from signallens.brief.agent import _merge_similar_stories

    def item(headline, event_type):
        return (NS(headline=headline, event_type=event_type), NS(title=headline))

    merged = _merge_similar_stories({
        1: [item("Razorpay launches Vulcan AI model for payment routing and fraud detection", "product_launch")],
        2: [item("Razorpay announces India's first AI payments foundation model named Vulcan", "other")],
        3: [item("Razorpay confidentially files for $600 million IPO", "funding")],
    }, "Razorpay")
    assert sorted(len(v) for v in merged.values()) == [1, 2]


def test_fact_numbers_must_appear_in_the_quote():
    from signallens.brief.agent import _numbers_supported

    assert _numbers_supported("PRIME plan for up to 20 employees ₹3499 per month", "PRIME Max. Employees: 20 ₹ 3499 / month")
    assert _numbers_supported("Threshold ₹5 lakh", "revenue more than ₹5,00,000?")
    assert not _numbers_supported("Effective fee 2.36%", "2% platform fee + 18% GST")
    assert not _numbers_supported("Threshold above ₹1Cr/month", "Accepting over ₹5L/month?")
    assert _numbers_supported("No setup fee", "There is no setup fee")


async def test_news_is_listed_unverified_when_triage_fails():
    world = make_world(BriefBrain(fail={"TriageOut"}))
    result = await _run(world)
    stories = result.data["developments"]
    assert stories and all(s["status"] == "unverified" for s in stories)
    assert any("could not be triaged" in w for w in result.data["warnings"])
    assert "**Unverified**" in result.markdown
