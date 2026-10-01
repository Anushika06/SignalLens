"""The monitoring plan contract (shared by the API and the pipeline).

This is exactly the ``MonitoringPlan`` shape in ``docs/api-contract.md``. The planner
produces it, the user edits and approves it, and activation materialises it into
entities, facts and sources.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

EntityKind = Literal["company", "product", "regulator", "person", "organization", "topic"]
EntityRole = Literal["subject", "competitor", "regulator", "partner", "us", "related"]
Importance = Literal["critical", "high", "medium", "low"]
ValueType = Literal["percent", "money", "number", "text", "list", "date", "boolean"]


class SourceValidation(BaseModel):
    ok: bool
    http_status: int | None = None
    robots_allowed: bool | None = None
    quality: Literal["ok", "degenerate", "blocked"] | None = None
    title: str | None = None
    note: str | None = None


class PlanDomain(BaseModel):
    industry: str = ""
    sector: str = ""
    geographies: list[str] = Field(default_factory=list)
    rationale: str = ""


class PlanEntity(BaseModel):
    ref: str
    name: str
    kind: EntityKind = "company"
    role: EntityRole = "related"
    aliases: list[str] = Field(default_factory=list)
    official_domains: list[str] = Field(default_factory=list)
    description: str = ""
    reason: str = ""
    enabled: bool = True


class PlanArea(BaseModel):
    key: str
    label: str
    description: str = ""
    importance: Importance = "medium"
    reason: str = ""
    route_to: list[str] = Field(default_factory=list)
    enabled: bool = True


class PlanAttribute(BaseModel):
    key: str
    entity_ref: str
    area: str
    label: str
    value_type: ValueType = "text"
    hint: str = ""
    source_refs: list[str] = Field(default_factory=list)
    enabled: bool = True


class PlanSource(BaseModel):
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
    enabled: bool = True
    validation: SourceValidation | None = None


class MonitoringPlan(BaseModel):
    summary: str = ""
    domain: PlanDomain = Field(default_factory=PlanDomain)
    entities: list[PlanEntity] = Field(default_factory=list)
    areas: list[PlanArea] = Field(default_factory=list)
    attributes: list[PlanAttribute] = Field(default_factory=list)
    sources: list[PlanSource] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
