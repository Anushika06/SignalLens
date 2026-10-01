"""Deterministic stand-ins for the web, the web archive and the models.

``FakeFetcher`` serves pages from a dict (plus sandbox pages from the database),
``FakeWayback`` serves archived captures, and ``Brain`` is a scripted model that answers
each typed request (plan, decision, extraction, materiality, triage, impact) the way a
competent model would, by reading the prompt it was given.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import Any

from signallens.fetch.http import FetchResult
from signallens.fetch.wayback import ArchiveCapture
from signallens.llm.base import ChatMessage


def page(url: str, html: str, status: int = 200) -> FetchResult:
    return FetchResult(url=url, final_url=url, status=status, content_type="text/html; charset=utf-8",
                       content=html.encode(), text=html, etag=None, last_modified=None, not_modified=False,
                       elapsed_ms=1)


class FakeFetcher:
    def __init__(self, pages: dict[str, str] | None = None, sandbox_resolver=None):
        self.pages = dict(pages or {})
        self.sandbox_resolver = sandbox_resolver
        self.calls: list[str] = []

    async def fetch(self, url: str, *, etag: str | None = None, last_modified: str | None = None,
                    check_robots: bool = True) -> FetchResult:
        self.calls.append(url)
        if url.startswith("sandbox://") and self.sandbox_resolver:
            found = await self.sandbox_resolver(url.removeprefix("sandbox://"))
            if found is None:
                return page(url, "not found", 404)
            result = page(url, found[0])
            result.from_sandbox = True
            return result
        if url in self.pages:
            return page(url, self.pages[url])
        return page(url, "<html><body>Not found</body></html>", 404)

    async def aclose(self) -> None:
        return None


class FakeWayback:
    def __init__(self, captures: dict[str, list[tuple[str, str]]]):
        self.captures = captures  # url -> [(timestamp, html)]

    async def list_captures(self, url: str, *, since=None, until=None, per="month", limit=24) -> list[ArchiveCapture]:
        out = []
        for ts, _html in self.captures.get(url, []):
            out.append(ArchiveCapture(timestamp=ts, captured_at=datetime.strptime(ts, "%Y%m%d%H%M%S").replace(tzinfo=UTC),
                                      original_url=url, status=200, digest=None, length=None))
        return out[:limit]

    async def fetch_capture(self, capture: ArchiveCapture) -> FetchResult:
        for ts, html in self.captures.get(capture.original_url, []):
            if ts == capture.timestamp:
                return page(capture.raw_url, html)
        return page(capture.raw_url, "missing", 404)

    async def aclose(self) -> None:
        return None


def _last_user(messages: list[ChatMessage]) -> str:
    return next((m.content for m in reversed(messages) if m.role == "user"), "")


def _page_text(prompt: str) -> str:
    m = re.search(r"<untrusted_content>\n(.*?)\n</untrusted_content>", prompt, re.S)
    return m.group(1) if m else prompt


PROMO_SENTENCE = "New merchants pay 0% platform fee for the first 90 days."
NEWS_A_URL = "https://news-a.example/nimbus-zeta"
NEWS_B_URL = "https://news-b.example/zeta-nimbus"
NEWS_C_URL = "https://news-c.example/fintech-roundup"
NEWS_D_URL = "https://news-d.example/cricket"
NEWS_A_QUOTE = "Nimbus Pay partners with Zeta Bank to offer instant settlements to merchants, the companies said on Monday."
NEWS_B_QUOTE = "Zeta Bank has partnered with payment gateway Nimbus Pay, and merchants will get settlement within minutes."
NEWS_C_QUOTE = "In other news, Nimbus Pay announced a partnership with Zeta Bank for faster settlement of merchant payments."


def article(title: str, lead: str) -> str:
    filler = " ".join(["The payments industry in India continues to grow quickly as merchants adopt digital methods."] * 6)
    return (f"<html><head><title>{title}</title></head><body><article><h1>{title}</h1><p>{lead}</p>"
            f"<p>{filler}</p><p>{filler}</p></article></body></html>")


FEE_RE = re.compile(r"(Accept domestic cards, UPI, netbanking and wallets at a flat ([\d.]+)% per successful transaction\.)")
INTL_RE = re.compile(r"International cards \| ([\d.]+)%")


class Brain:
    """Scripted model. ``calls`` counts requests per schema for assertions."""

    def __init__(self) -> None:
        self.calls: dict[str, int] = {}
        self.plan_sources: list[dict[str, Any]] | None = None
        self.triage_items: dict[str, dict[str, Any]] = {}  # url substring -> triage fields
        self.impact_severity = "high"

    def __call__(self, system: str, messages: list[ChatMessage], schema: dict | None, name: str):
        self.calls[name] = self.calls.get(name, 0) + 1
        prompt = _last_user(messages)
        handler = getattr(self, f"on_{name}", None)
        if handler is None:
            raise AssertionError(f"Brain has no answer for {name}")
        return handler(system, messages, prompt)

    # --- planner / investigator decisions ------------------------------------------------------
    def on_Decision(self, system: str, messages: list[ChatMessage], prompt: str):
        observations = sum(1 for m in messages if m.role == "user" and m.content.startswith("OBSERVATION"))
        guardrails = sum(1 for m in messages if m.role == "user" and m.content.startswith("GUARDRAIL"))
        if "planning analyst" in system:
            if observations == 0:
                return {"thought": "Open the official pricing page to confirm it exists.", "action": "open_page",
                        "args": {"url": "sandbox://nimbus-pay-pricing", "focus": ["fee"]}}
            return {"thought": "I have what I need.", "action": "finish",
                    "args": {"notes": "Nimbus Pay (fictional) official pricing page at sandbox://nimbus-pay-pricing "
                                      "shows a 2% standard fee."}}
        # investigator
        first = messages[0].content
        finish = {"thought": "Evidence is sufficient.", "action": "finish",
                  "args": {"conclusion": "The sources state the new terms.", "claim_holds": "yes",
                           "occurred_at": "2026-09-27", "contradictions": [], "open_questions": []}}
        if "Zeta Bank" in first:  # news event: open another publisher and quote it
            if observations == 0:
                return {"thought": "Look for a third, independent report.", "action": "open_page",
                        "args": {"url": NEWS_C_URL, "focus": ["Zeta"]}}
            if observations == 1:
                return {"thought": "Quote the independent report.", "action": "record_evidence",
                        "args": {"url": NEWS_C_URL, "quote": NEWS_C_QUOTE, "stance": "supports"}}
            return finish
        opened = re.search(r"detection source already opened for you: (\S+)\)", first)
        if observations == 0 and opened and guardrails == 0:
            quote = PROMO_SENTENCE if "90 days" in first else self.current_fee_quote
            if quote:
                return {"thought": "Record the official page as primary evidence.", "action": "record_evidence",
                        "args": {"url": opened.group(1), "quote": quote, "stance": "supports"}}
        return finish

    current_fee_quote: str | None = None

    # --- plan -----------------------------------------------------------------------------------
    def on_MonitoringPlanOut(self, system, messages, prompt):
        return {
            "summary": "Monitor Nimbus Pay pricing, products and partnerships.",
            "domain": {"industry": "Financial technology", "sector": "Payments", "geographies": ["India"],
                       "rationale": "Payment gateway"},
            "entities": [
                {"ref": "nimbus", "name": "Nimbus Pay", "kind": "company", "role": "subject",
                 "official_domains": ["nimbuspay.example"], "description": "Payment gateway", "reason": "Subject"},
                {"ref": "rbi", "name": "Reserve Bank of India", "kind": "regulator", "role": "regulator",
                 "aliases": ["RBI"], "official_domains": ["rbi.org.in"], "reason": "Regulates payment aggregators"},
            ],
            "areas": [
                {"key": "pricing", "label": "Pricing & fees", "importance": "critical", "route_to": ["Strategy", "Product"]},
                {"key": "partnerships", "label": "Partnerships", "importance": "high", "route_to": ["Sales & BD"]},
            ],
            "attributes": [
                {"key": "pricing.standard_domestic_fee", "entity_ref": "nimbus", "area": "pricing",
                 "label": "Standard domestic fee", "value_type": "percent",
                 "hint": "Standard plan fee for domestic methods", "source_refs": ["pricing-page"]},
                {"key": "pricing.international_card_fee", "entity_ref": "nimbus", "area": "pricing",
                 "label": "International card fee", "value_type": "percent", "hint": "International cards fee",
                 "source_refs": ["pricing-page"]},
            ],
            "sources": self.plan_sources or [
                {"ref": "pricing-page", "kind": "page", "url": "sandbox://nimbus-pay-pricing", "entity_ref": "nimbus",
                 "areas": ["pricing"], "authority": "official", "priority": "high", "check_every_hours": 12,
                 "backfill": True, "reason": "Official pricing page"},
                {"ref": "news", "kind": "news", "query": "Nimbus Pay", "entity_ref": "nimbus",
                 "areas": ["partnerships", "pricing"], "authority": "independent", "priority": "high",
                 "check_every_hours": 3, "reason": "General coverage"},
            ],
            "open_questions": ["Should we also track Nimbus Pay's international business?"],
        }

    # --- extraction -----------------------------------------------------------------------------
    def on_ExtractionOut(self, system, messages, prompt):
        text = _page_text(prompt)
        values = []
        m = FEE_RE.search(text)
        if m:
            conditions = "0% platform fee for the first 90 days for new merchants" if "first 90 days" in text else None
            values.append({"key": "pricing.standard_domestic_fee", "found": True,
                           "value_display": f"{m.group(2)}% per transaction" + (f"; {conditions}" if conditions else ""),
                           "number": float(m.group(2)), "unit": "%", "conditions": conditions, "quote": m.group(1)})
            self.current_fee_quote = m.group(1)
        i = INTL_RE.search(text)
        if i:
            values.append({"key": "pricing.international_card_fee", "found": True,
                           "value_display": f"{i.group(1)}% per transaction", "number": float(i.group(1)), "unit": "%",
                           "quote": f"International cards | {i.group(1)}%", "same_as_previous": None})
        return {"values": values}

    # --- materiality ------------------------------------------------------------------------------
    def on_MaterialityOut(self, system, messages, prompt):
        diff = _page_text(prompt)
        hunks = re.split(r"(?m)^@@ ", diff)
        changes, noise = [], []
        for block in hunks[1:]:
            num = int(block.split()[0])
            if "first 90 days" in block:
                changes.append({"hunk_ids": [num], "title": "New 0% platform-fee offer for the first 90 days",
                                "summary": "Nimbus Pay now charges new merchants no platform fee for 90 days.",
                                "area": "pricing", "event_type": "pricing", "before": None,
                                "after": "0% platform fee for the first 90 days", "materiality": "high",
                                "reason": "Introductory pricing changes acquisition economics."})
            elif "Webinar" in block:
                changes.append({"hunk_ids": [num], "title": "Webinar banner added", "summary": "Marketing banner.",
                                "area": "pricing", "event_type": "content_change", "materiality": "none",
                                "reason": "Marketing copy only."})
            else:
                noise.append(num)
        return {"changes": changes, "noise_hunk_ids": noise, "noise_reason": "Already captured or cosmetic."}

    # --- triage -------------------------------------------------------------------------------------
    def on_TriageOut(self, system, messages, prompt):
        items = []
        for m in re.finditer(r"^\[(\d+)\] (.*)\n    publisher: .*? \| url: (\S+)", _page_text(prompt), re.M):
            idx, url = int(m.group(1)), m.group(3)
            spec = next((v for k, v in self.triage_items.items() if k in url), None)
            if spec is None:
                items.append({"id": idx, "relevant": False, "reason": "Not about the monitored entity"})
            else:
                items.append({"id": idx, "relevant": True, **spec})
        return {"items": items}

    # --- impact ---------------------------------------------------------------------------------------
    def on_ImpactOut(self, system, messages, prompt):
        claim = re.search(r"CLAIM: (.*)", prompt)
        return {
            "headline": (claim.group(1) if claim else "Change detected")[:120],
            "change_label": "Pricing change" if "fee" in prompt.lower() else "New partnership",
            "what_changed": claim.group(1) if claim else "A change was detected.",
            "why_it_matters": "Orbit Payments competes with Nimbus Pay for SMB merchants; cheaper onboarding pulls "
                              "new merchants toward Nimbus Pay.",
            "affected_teams": ["Strategy", "Product", "Nonexistent Team"],
            "considerations": ["Review our SMB onboarding offer."],
            "assumptions": ["The offer applies to all new merchants."],
            "watch_next": ["Whether the offer is extended beyond 90 days."],
            "severity": self.impact_severity,
            "severity_rationale": "Direct competitor pricing move.",
            "proposed_actions": [],
        }


def dumps(value: Any) -> str:
    return json.dumps(value)
