"""Typed outputs the models must produce. The gateway validates every response against these."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------------------
# Planner
# ---------------------------------------------------------------------------------------


class PlannerFinish(BaseModel):
    notes: str = Field(
        description="Everything learned that matters for the plan: who the subject is, official domains, "
        "verified page URLs and what each shows, products, competitors, regulators, recent developments."
    )


class PlanDomainOut(BaseModel):
    industry: str
    sector: str
    geographies: list[str] = Field(default_factory=list)
    rationale: str = ""


class PlanEntityOut(BaseModel):
    ref: str = Field(description="short lowercase slug, unique within the plan, e.g. 'razorpay'")
    name: str
    kind: Literal["company", "product", "regulator", "person", "organization", "topic"] = "company"
    role: Literal["subject", "competitor", "regulator", "partner", "related"] = "related"
    aliases: list[str] = Field(default_factory=list)
    official_domains: list[str] = Field(default_factory=list, description="bare domains, e.g. 'razorpay.com'")
    description: str = ""
    reason: str = ""


class PlanAreaOut(BaseModel):
    key: str = Field(description="short lowercase key, e.g. 'pricing'")
    label: str
    description: str = ""
    importance: Literal["critical", "high", "medium", "low"] = "medium"
    reason: str = ""
    route_to: list[str] = Field(default_factory=list, description="team names from the provided list")


class PlanAttributeOut(BaseModel):
    key: str = Field(description="'<area>.<slug>', e.g. 'pricing.standard_domestic_fee'")
    entity_ref: str
    area: str
    label: str
    value_type: Literal["percent", "money", "number", "text", "list", "date", "boolean"] = "text"
    hint: str = Field(description="precisely what to extract, incl. conditions to capture")
    source_refs: list[str] = Field(default_factory=list)


class PlanSourceOut(BaseModel):
    ref: str
    kind: Literal["page", "news"]
    url: str | None = None
    query: str | None = None
    entity_ref: str
    areas: list[str] = Field(default_factory=list)
    authority: Literal["official", "regulator", "independent", "community"] = "official"
    priority: Literal["high", "medium", "low"] = "medium"
    check_every_hours: float = 12
    backfill: bool = False
    reason: str = ""


class MonitoringPlanOut(BaseModel):
    summary: str
    domain: PlanDomainOut
    entities: list[PlanEntityOut]
    areas: list[PlanAreaOut]
    attributes: list[PlanAttributeOut] = Field(default_factory=list)
    sources: list[PlanSourceOut]
    open_questions: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------------------
# Scout: attribute extraction
# ---------------------------------------------------------------------------------------


class ExtractedValueOut(BaseModel):
    key: str
    found: bool
    value_display: str | None = Field(None, description="concise human-readable value incl. essential conditions")
    number: float | None = None
    unit: str | None = None
    conditions: str | None = None
    quote: str | None = Field(None, description="exact text copied verbatim from the page")
    same_as_previous: bool | None = None


class ExtractionOut(BaseModel):
    values: list[ExtractedValueOut]


# ---------------------------------------------------------------------------------------
# Analyst: materiality of page changes
# ---------------------------------------------------------------------------------------


class ChangeAssessmentOut(BaseModel):
    hunk_ids: list[int] = Field(default_factory=list)
    title: str = Field(description="neutral factual title, e.g. 'New 0% platform-fee offer for first 90 days'")
    summary: str
    area: str
    event_type: str
    before: str | None = None
    after: str | None = None
    materiality: Literal["none", "low", "medium", "high", "critical"]
    reason: str


class MaterialityOut(BaseModel):
    changes: list[ChangeAssessmentOut] = Field(default_factory=list)
    noise_hunk_ids: list[int] = Field(default_factory=list)
    noise_reason: str | None = None


# ---------------------------------------------------------------------------------------
# Scout: news triage
# ---------------------------------------------------------------------------------------


class TriageItemOut(BaseModel):
    id: int
    relevant: bool
    entity: str | None = Field(None, description="exact name of the monitored entity it is about")
    event_type: str = "other"
    area: str = "general"
    headline: str = ""
    summary: str = ""
    claim: str = Field("", description="one checkable statement of what happened")
    counterparty: str | None = None
    product: str | None = None
    person: str | None = None
    round_or_amount: str | None = None
    topic: str | None = None
    occurred_at: str | None = Field(None, description="ISO date if the article states when it happened")
    materiality: Literal["none", "low", "medium", "high", "critical"] = "none"
    reason: str = ""


class TriageOut(BaseModel):
    items: list[TriageItemOut]


# ---------------------------------------------------------------------------------------
# Verifier
# ---------------------------------------------------------------------------------------


class InvestigationFinish(BaseModel):
    conclusion: str = Field(description="2-4 sentences: what the evidence shows")
    claim_holds: Literal["yes", "no", "partly", "unclear"]
    corrected_statement: str | None = Field(None, description="the accurate statement if the claim needs correcting")
    occurred_at: str | None = Field(None, description="ISO date it happened or takes effect, if found")
    contradictions: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------------------
# Impact analyst
# ---------------------------------------------------------------------------------------


class ProposedActionOut(BaseModel):
    action_type: Literal["send_external_email", "share_report_externally", "post_external_webhook"]
    title: str
    reason: str
    recipient_hint: str | None = None
    draft: str = ""


class ImpactOut(BaseModel):
    headline: str
    change_label: str
    what_changed: str = Field(description="facts only, from the evidence")
    previous_state: str | None = None
    current_state: str | None = None
    why_it_matters: str = Field(description="assessment for THIS company; interpretation, not fact")
    affected_teams: list[str] = Field(default_factory=list)
    considerations: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    watch_next: list[str] = Field(default_factory=list)
    severity: Literal["critical", "high", "medium", "low"]
    severity_rationale: str = ""
    proposed_actions: list[ProposedActionOut] = Field(default_factory=list)
