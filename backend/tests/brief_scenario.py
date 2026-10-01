"""A deterministic world for brief tests: a fictional payment company, its pages, the archive,
search results and a scripted model that answers each brief schema by reading its prompt."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import Any

from signallens.llm.base import ChatMessage, LLMError
from signallens.llm.fake import ScriptedLLM
from signallens.runtime.gateway import ModelGateway
from signallens.search.base import SearchResult
from signallens.search.fake import StaticSearch
from tests.integration.fakes import FakeFetcher, FakeWayback

DOMAIN = "nimbuspay.in"
HOME = f"https://{DOMAIN}/"
PRICING = f"https://{DOMAIN}/pricing"
NEWSROOM = f"https://{DOMAIN}/newsroom"
PRESS = f"https://{DOMAIN}/newsroom/zeta-bank-partnership"
NEWS_ET = "https://economictimes.indiatimes.com/tech/nimbus-zeta"
NEWS_INC = "https://inc42.com/buzz/nimbus-pay-zeta-bank"
NEWS_OTHER = "https://cricnews.example.com/match"

FILLER = " ".join(["Nimbus Pay helps Indian businesses accept online payments with cards, UPI and netbanking."] * 4)
FEE_NOW = "Standard plan: 2.5% per successful transaction"
FEE_THEN = "Standard plan: 2% per successful transaction"
PROMO = "New merchants pay 0% platform fee for the first 90 days."
INTL = "International cards: 3.5% per transaction"
PRESS_QUOTE = "Nimbus Pay has partnered with Zeta Bank to offer instant settlements"
ET_QUOTE = "Nimbus Pay partners with Zeta Bank for instant merchant settlements"
INC_QUOTE = "Zeta Bank and Nimbus Pay announced a partnership for instant settlement"


def html(title: str, *paragraphs: str) -> str:
    body = "".join(f"<p>{p}</p>" for p in paragraphs)
    return f"<html><head><title>{title}</title></head><body><main><h1>{title}</h1>{body}</main></body></html>"


PAGES = {
    PRICING: html("Pricing", f"{FEE_NOW}.", f"{INTL}.", PROMO, FILLER),
    HOME: html("Nimbus Pay", "Nimbus Pay is a payment gateway for Indian SMBs.", FILLER),
    NEWSROOM: html("Newsroom", f"{PRESS_QUOTE}.", FILLER),
}


def archive_ts(days_ago: int = 365) -> str:
    return (datetime.now(UTC) - timedelta(days=days_ago)).strftime("%Y%m%d%H%M%S")


def make_wayback() -> FakeWayback:
    return FakeWayback({PRICING: [(archive_ts(), html("Pricing", f"{FEE_THEN}.", f"{INTL}.", FILLER))]})


def _r(url: str, title: str, snippet: str, days_ago: int | None = None) -> SearchResult:
    when = datetime.now(UTC) - timedelta(days=days_ago) if days_ago is not None else None
    return SearchResult(url=url, title=title, snippet=snippet, published_at=when)


def search_handler(query: str, options: dict[str, Any]) -> list[SearchResult]:
    if options.get("include_domains"):
        return [_r(PRICING, "Pricing | Nimbus Pay", "Standard plan 2.5% per successful transaction"),
                _r(NEWSROOM, "Newsroom | Nimbus Pay", "Latest announcements"),
                _r(PRESS, "Nimbus Pay partners with Zeta Bank", f"{PRESS_QUOTE}, the company said.", 10)]
    if options.get("topic") == "news":
        return [_r(NEWS_ET, "Nimbus Pay ties up with Zeta Bank", f"{ET_QUOTE}, according to the companies.", 9),
                _r(NEWS_INC, "Zeta Bank, Nimbus Pay partner", f"{INC_QUOTE} on Monday.", 8),
                _r(NEWS_OTHER, "India win by five wickets", "Cricket match report.", 3)]
    return [_r("https://en.wikipedia.org/wiki/Nimbus_Pay", "Nimbus Pay - Wikipedia", "Nimbus Pay is an Indian fintech."),
            _r(HOME, "Nimbus Pay - Payment gateway for India", "Accept payments online with Nimbus Pay."),
            _r(PRICING, "Pricing | Nimbus Pay", "Standard plan 2.5% per successful transaction")]


def _last_user(messages: list[ChatMessage]) -> str:
    return next((m.content for m in reversed(messages) if m.role == "user"), "")


def _fenced(prompt: str) -> list[str]:
    return re.findall(r"<untrusted_content>\n(.*?)\n</untrusted_content>", prompt, re.S)


class BriefBrain:
    """Scripted model for the brief schemas. ``calls`` counts requests per schema."""

    def __init__(self, *, fail: set[str] | None = None):
        self.calls: dict[str, int] = {}
        self.prompts: dict[str, list[str]] = {}
        self.systems: dict[str, list[str]] = {}
        self.fail = fail or set()

    def __call__(self, system: str, messages: list[ChatMessage], schema: dict | None, name: str):
        self.calls[name] = self.calls.get(name, 0) + 1
        prompt = _last_user(messages)
        self.prompts.setdefault(name, []).append(prompt)
        self.systems.setdefault(name, []).append(system)
        if name in self.fail or "*" in self.fail:
            raise LLMError("scripted outage", retryable=False)
        return getattr(self, f"on_{name}")(prompt)

    def on_CompanyNameOut(self, prompt: str):
        return {"company": "Nimbus Pay", "your_company": ""}

    def on_ResolveOut(self, prompt: str):
        return {"company_name": "Nimbus Pay", "official_domain": DOMAIN,
                "description": "Nimbus Pay is a payment gateway for Indian SMBs.", "industry": "Payments",
                "ambiguity_note": "",
                "pages": [
                    {"url": PRICING, "kind": "pricing", "reason": "Fees", "watch": ["standard fee", "international fee"]},
                    {"url": NEWSROOM, "kind": "newsroom", "reason": "Announcements", "watch": ["partnerships"]},
                    {"url": "https://other-site.example.com/x", "kind": "other", "reason": "off-domain", "watch": []},
                ]}

    def on_ExtractOut(self, prompt: str):
        text = _fenced(prompt)[0]
        facts = []
        if FEE_NOW in text:
            facts.append({"category": "pricing", "label": "Standard domestic fee", "value": "2.5% per transaction",
                          "quote": FEE_NOW})
            facts.append({"category": "pricing", "label": "Introductory offer", "value": "0% platform fee, 90 days",
                          "quote": PROMO})
            facts.append({"category": "pricing", "label": "Invented fee", "value": "1.1%",
                          "quote": "Enterprise plan: 1.1% per successful transaction"})  # hallucinated
        if PRESS_QUOTE in text:
            facts.append({"category": "partnership", "label": "Zeta Bank partnership", "value": "instant settlements",
                          "quote": PRESS_QUOTE})
        return {"page_summary": "Official page.", "facts": facts}

    def on_HistoryOut(self, prompt: str):
        ids = dict((label, int(i)) for i, label in re.findall(r"^\[(\d+)\] ([^:]+):", prompt, re.M))
        facts = []
        if "Standard domestic fee" in ids:
            facts.append({"id": ids["Standard domestic fee"], "present": True, "value": "2% per transaction",
                          "quote": FEE_THEN})
        if "Introductory offer" in ids:
            facts.append({"id": ids["Introductory offer"], "present": False, "value": "", "quote": ""})
        return {"facts": facts, "other_changes": [
            {"category": "pricing", "title": "Made-up change", "before_quote": "Old plan was free forever",
             "after_quote": FEE_NOW},
            {"category": "pricing", "title": "Promo launched", "before_quote": "", "after_quote": PROMO},
            {"category": "pricing", "title": "Unrelated pairing", "before_quote": INTL, "after_quote": PROMO}]}

    def on_TriageOut(self, prompt: str):
        items = []
        for idx, url in re.findall(r"^\[(\d+)\] .*\n    publisher: .*? \| url: (\S+)", _fenced(prompt)[0], re.M):
            i = int(idx)
            if "cricnews" in url:
                items.append({"id": i, "relevant": False})
                continue
            quote = PRESS_QUOTE if url == PRESS else ET_QUOTE if url == NEWS_ET else INC_QUOTE
            items.append({"id": i, "relevant": True, "story": 1, "headline": "Nimbus Pay partners with Zeta Bank",
                          "claim": "Nimbus Pay and Zeta Bank partnered for instant settlements.",
                          "event_type": "partnership", "materiality": "high", "occurred_at": "", "quote": quote})
        return {"items": items}

    def on_ImpactOut(self, prompt: str):
        return {
            "executive_summary": "Nimbus Pay raised its standard fee and partnered with Zeta Bank.",
            "facts": [{"statement": "The standard fee rose from 2% to 2.5%.", "refs": ["C1", "S1"]},
                      {"statement": "An uncited claim.", "refs": ["Z9"]}],
            "assessment": ["This opens room to win price-sensitive SMBs."],
            "actions": [{"action": "Pitch our 2% plan to Nimbus Pay merchants.", "owner": "Sales", "why": "Price gap"},
                        {"action": "Review settlement speed.", "owner": "Product", "why": "Zeta partnership"},
                        {"action": "Brief leadership.", "owner": "Strategy", "why": "Pricing shift"}],
            "change_notes": [{"id": "C1", "text": "A 25% price increase for standard merchants."}],
            "headlines": [{"id": "N1", "text": "Nimbus Pay and Zeta Bank partner on instant settlement"}],
            "watch_next": ["Whether other gateways follow."], "assumptions": [],
        }


def make_llm(brain: BriefBrain) -> ModelGateway:
    return ModelGateway(ScriptedLLM(brain), provider_name="scripted", fast_model="scripted-fast",
                        reasoning_model="scripted-reasoning")


def make_world(brain: BriefBrain | None = None) -> dict[str, Any]:
    brain = brain or BriefBrain()
    return {"brain": brain, "llm": make_llm(brain), "search": StaticSearch(search_handler),
            "fetcher": FakeFetcher(PAGES), "wayback": make_wayback()}
