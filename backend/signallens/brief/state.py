"""What a brief run gathers, shared by the agent (which fills it) and the renderer."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any

STATUS_LABELS = {
    "confirmed": "Confirmed",
    "corroborated": "Corroborated",
    "single_source": "Single source",
    "conflicting": "Conflicting",
    "unverified": "Unverified",
}


@dataclass
class Company:
    query: str
    name: str
    domain: str | None = None
    description: str = ""
    industry: str = ""
    ambiguity_note: str = ""
    resolved_by: str = "model"  # model | heuristic


@dataclass
class PageInfo:
    url: str
    kind: str
    reason: str
    watch: list[str] = field(default_factory=list)
    final_url: str | None = None
    ok: bool = False
    problem: str | None = None
    via: str | None = None
    words: int = 0
    summary: str = ""


@dataclass
class Fact:
    id: str  # S1, S2 ...
    category: str
    label: str
    value: str
    quote: str
    url: str
    page_kind: str


@dataclass
class Change:
    id: str  # C1, C2 ...
    kind: str  # changed | added | other
    category: str
    label: str
    before: str
    after: str
    before_quote: str
    after_quote: str
    url: str
    archive_url: str
    captured_on: date
    status: str  # confirmed | unverified
    note: str = ""


@dataclass
class Source:
    publisher: str
    url: str
    title: str
    quote: str
    quote_verified: bool
    source_class: str  # primary | independent | community
    published: date | None = None


@dataclass
class Story:
    id: str  # N1, N2 ...
    headline: str
    claim: str
    event_type: str
    materiality: str
    when: date | None
    status: str
    status_summary: str
    sources: list[Source] = field(default_factory=list)


@dataclass
class BriefState:
    company: Company
    pages: list[PageInfo] = field(default_factory=list)
    facts: list[Fact] = field(default_factory=list)
    changes: list[Change] = field(default_factory=list)
    stories: list[Story] = field(default_factory=list)
    history_note: str = ""  # why history is missing/partial, when it is
    news_screened: int = 0
    impact: dict[str, Any] | None = None
    warnings: list[str] = field(default_factory=list)
    dropped_quotes: int = 0

    def as_data(self) -> dict[str, Any]:
        def clean(v: Any) -> Any:
            if isinstance(v, date):
                return v.isoformat()
            if isinstance(v, dict):
                return {k: clean(x) for k, x in v.items()}
            if isinstance(v, list):
                return [clean(x) for x in v]
            return v

        return clean({
            "company": asdict(self.company),
            "pages": [asdict(p) for p in self.pages],
            "facts": [asdict(f) for f in self.facts],
            "changes": [asdict(c) for c in self.changes],
            "developments": [asdict(s) for s in self.stories],
            "history_note": self.history_note,
            "news_screened": self.news_screened,
            "impact": self.impact,
            "warnings": self.warnings,
            "unverified_quotes_dropped": self.dropped_quotes,
        })
