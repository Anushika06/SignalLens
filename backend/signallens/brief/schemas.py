"""Typed model outputs for the brief agent.

Kept flat and small on purpose: NVIDIA NIM's guided decoding marks every property as
required, so each field has a sensible empty value and no field is a free-form mapping.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Category = Literal["pricing", "product", "partnership", "funding", "regulatory", "leadership", "hiring",
                   "customers", "company", "other"]
PageKind = Literal["pricing", "products", "newsroom", "legal", "about", "careers", "investors", "homepage", "other"]
Team = Literal["Strategy", "Product", "Sales", "Compliance", "Marketing"]


class CompanyNameOut(BaseModel):
    company: str = Field(description="the company the user wants analysed, as a name or website")
    your_company: str = Field("", description="the requester's own company if the text says it, else empty")


class PagePickOut(BaseModel):
    url: str
    kind: PageKind = "other"
    reason: str = ""
    watch: list[str] = Field(default_factory=list, description="2-5 specific things to extract from this page")


class ResolveOut(BaseModel):
    company_name: str
    official_domain: str = Field(description="bare registrable domain, e.g. razorpay.com")
    description: str = Field(description="1-2 factual sentences: what the company does, for whom, where")
    industry: str = ""
    pages: list[PagePickOut] = Field(default_factory=list)
    ambiguity_note: str = Field("", description="if the name was ambiguous: which entity was chosen and why")


class FactOut(BaseModel):
    category: Category = "other"
    label: str = Field(description="short stable name, e.g. 'Standard domestic transaction fee'")
    value: str = Field(description="concise value including conditions that change its meaning")
    quote: str = Field(description="exact words copied from the page that show the value")


class ExtractOut(BaseModel):
    page_summary: str = Field("", description="one sentence: what this page shows")
    facts: list[FactOut] = Field(default_factory=list)


class OldFactOut(BaseModel):
    id: int
    present: bool = Field(description="does the ARCHIVED page state this attribute at all?")
    value: str = ""
    quote: str = Field("", description="exact words copied from the ARCHIVED text")


class OtherChangeOut(BaseModel):
    category: Category = "other"
    title: str
    before_quote: str = Field(description="exact words copied from the ARCHIVED text")
    after_quote: str = Field(description="exact words copied from the CURRENT text")


class HistoryOut(BaseModel):
    facts: list[OldFactOut] = Field(default_factory=list)
    other_changes: list[OtherChangeOut] = Field(default_factory=list)


class TriageItemOut(BaseModel):
    id: int
    relevant: bool
    story: int = Field(0, description="items reporting the same event share one story number")
    headline: str = ""
    claim: str = Field("", description="one checkable statement of what happened")
    event_type: str = "other"
    materiality: Literal["none", "low", "medium", "high", "critical"] = "none"
    occurred_at: str = Field("", description="ISO date of the event if stated, else empty")
    quote: str = Field("", description="exact words copied from THIS item's text that support the claim")


class TriageOut(BaseModel):
    items: list[TriageItemOut] = Field(default_factory=list)


class CitedFactOut(BaseModel):
    statement: str
    refs: list[str] = Field(default_factory=list, description="ids such as S1, C2, N3 from the inputs")


class ActionOut(BaseModel):
    action: str
    owner: Team
    why: str = ""


class NoteOut(BaseModel):
    id: str
    text: str


class ImpactOut(BaseModel):
    executive_summary: str = Field(description="one paragraph, 3-5 sentences")
    facts: list[CitedFactOut] = Field(default_factory=list)
    assessment: list[str] = Field(default_factory=list, description="2-4 bullets of interpretation for the reader")
    actions: list[ActionOut] = Field(default_factory=list)
    change_notes: list[NoteOut] = Field(default_factory=list, description="per change id: why it changed / matters")
    headlines: list[NoteOut] = Field(default_factory=list, description="per development id: headline in the language")
    watch_next: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
