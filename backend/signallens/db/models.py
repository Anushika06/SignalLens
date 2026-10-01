"""SignalLens data model.

The core chain is::

    Entity ─< Fact ─< StateVersion          (what we believe is true, over time)
       │
       └─< Event ─< Claim ─< Evidence       (what changed, and why we believe it)
              └── IntelligenceReport        (what it means for us, and who needs to know)

Around it: tenancy (Organization, User, Workspace, Team), configuration
(MonitoringPolicy, Source, LearnedRule), collection (Document, SourceSnapshot,
SourceCheck), the agent runtime's audit trail (AgentRun, RunStep, Investigation),
delivery (Notification, Approval, UserFeedback) and background execution (Job).

Enumerations are stored as short strings (validated at the API/pipeline layer) so the
schema can evolve without enum migrations. Every tenant-owned row carries
``workspace_id`` and every query filters on it.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from signallens.db.base import Base, created_at_col, utcnow, uuid_pk

# ---------------------------------------------------------------------------------------
# Tenancy
# ---------------------------------------------------------------------------------------


class Organization(Base):
    __tablename__ = "organizations"
    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = created_at_col()


class User(Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = uuid_pk()
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    # None for accounts that only sign in through single sign-on.
    password_hash: Mapped[str | None] = mapped_column(String(300), default=None)
    auth_provider: Mapped[str] = mapped_column(String(16), default="password")  # password | oidc
    sso_subject: Mapped[str | None] = mapped_column(String(300), default=None, unique=True)
    created_at: Mapped[datetime] = created_at_col()


class Workspace(Base):
    """A monitoring programme, e.g. "Payments competitive landscape"."""

    __tablename__ = "workspaces"
    id: Mapped[uuid.UUID] = uuid_pk()
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(32), default="setup")
    # "Us": our company, products, markets, competitors (spec review C1).
    profile: Mapped[dict[str, Any]] = mapped_column(default=dict)
    settings: Mapped[dict[str, Any]] = mapped_column(default=dict)
    last_digest_at: Mapped[datetime | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


class WorkspaceMember(Base):
    __tablename__ = "workspace_members"
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    role: Mapped[str] = mapped_column(String(32), default="member")
    last_seen_at: Mapped[datetime | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = created_at_col()


class Team(Base):
    """Who receives what: routing target for intelligence (spec review C1, C11)."""

    __tablename__ = "teams"
    id: Mapped[uuid.UUID] = uuid_pk()
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    areas: Mapped[list[str]] = mapped_column(default=list)
    members: Mapped[list[str]] = mapped_column(default=list)
    slack_webhook_url: Mapped[str | None] = mapped_column(Text, default=None)
    # Recipients of the team's email digest and immediate email alerts.
    emails: Mapped[list[str]] = mapped_column(default=list)
    created_at: Mapped[datetime] = created_at_col()


# ---------------------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------------------


class MonitoringPolicy(Base):
    """A versioned monitoring plan. ``spec`` holds the full MonitoringPlan JSON."""

    __tablename__ = "monitoring_policies"
    id: Mapped[uuid.UUID] = uuid_pk()
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(32), default="planning")
    request_text: Mapped[str] = mapped_column(Text)
    spec: Mapped[dict[str, Any] | None] = mapped_column(default=None)
    planner_run_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    error: Mapped[str | None] = mapped_column(Text, default=None)
    created_by: Mapped[uuid.UUID | None] = mapped_column(default=None)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(default=None)
    approved_at: Mapped[datetime | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = created_at_col()


class LearnedRule(Base):
    """A visible, reversible policy adjustment derived from user feedback (spec review C10)."""

    __tablename__ = "learned_rules"
    id: Mapped[uuid.UUID] = uuid_pk()
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(40))
    scope: Mapped[dict[str, Any]] = mapped_column(default=dict)
    effect: Mapped[dict[str, Any]] = mapped_column(default=dict)
    explanation: Mapped[str] = mapped_column(Text)
    evidence_count: Mapped[int] = mapped_column(Integer, default=1)
    feedback_ids: Mapped[list[str]] = mapped_column(default=list)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)
    revoked_at: Mapped[datetime | None] = mapped_column(default=None)


# ---------------------------------------------------------------------------------------
# World: entities and relationships
# ---------------------------------------------------------------------------------------


class Entity(Base):
    """Anything we track: companies, products, regulators, people, topics.

    One polymorphic table (``kind``) instead of a ``companies`` table keeps the model
    domain-agnostic (spec review C14): pharma needs drugs, automotive needs vehicle models.
    """

    __tablename__ = "entities"
    __table_args__ = (UniqueConstraint("workspace_id", "name_key"),)
    id: Mapped[uuid.UUID] = uuid_pk()
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(32), default="company")
    role: Mapped[str] = mapped_column(String(32), default="related")
    name: Mapped[str] = mapped_column(String(300))
    name_key: Mapped[str] = mapped_column(String(300))
    aliases: Mapped[list[str]] = mapped_column(default=list)
    official_domains: Mapped[list[str]] = mapped_column(default=list)
    description: Mapped[str] = mapped_column(Text, default="")
    profile: Mapped[dict[str, Any]] = mapped_column(default=dict)
    plan_ref: Mapped[str | None] = mapped_column(String(120), default=None)
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


class EntityRelationship(Base):
    __tablename__ = "entity_relationships"
    __table_args__ = (UniqueConstraint("subject_id", "predicate", "object_id"),)
    id: Mapped[uuid.UUID] = uuid_pk()
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    subject_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("entities.id", ondelete="CASCADE"))
    predicate: Mapped[str] = mapped_column(String(60))
    object_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("entities.id", ondelete="CASCADE"))
    properties: Mapped[dict[str, Any]] = mapped_column(default=dict)
    event_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    first_seen_at: Mapped[datetime] = mapped_column(default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(default=utcnow)


# ---------------------------------------------------------------------------------------
# Collection
# ---------------------------------------------------------------------------------------


class Source(Base):
    """Something we check on a schedule: a page (snapshot + diff) or a news query (stream)."""

    __tablename__ = "sources"
    __table_args__ = (Index("ix_sources_due", "active", "next_check_at"),)
    id: Mapped[uuid.UUID] = uuid_pk()
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    policy_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("entities.id", ondelete="SET NULL"), default=None)
    kind: Mapped[str] = mapped_column(String(16))  # page | news
    url: Mapped[str | None] = mapped_column(Text, default=None)
    query: Mapped[str | None] = mapped_column(Text, default=None)
    areas: Mapped[list[str]] = mapped_column(default=list)
    authority: Mapped[str] = mapped_column(String(32), default="independent")
    priority: Mapped[str] = mapped_column(String(16), default="medium")
    check_every_minutes: Mapped[int] = mapped_column(Integer, default=720)
    current_interval_minutes: Mapped[int] = mapped_column(Integer, default=720)
    next_check_at: Mapped[datetime | None] = mapped_column(default=None)
    last_checked_at: Mapped[datetime | None] = mapped_column(default=None)
    last_changed_at: Mapped[datetime | None] = mapped_column(default=None)
    last_outcome: Mapped[str | None] = mapped_column(String(32), default=None)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    etag: Mapped[str | None] = mapped_column(Text, default=None)
    last_modified: Mapped[str | None] = mapped_column(Text, default=None)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    backfill: Mapped[bool] = mapped_column(Boolean, default=False)
    baselined: Mapped[bool] = mapped_column(Boolean, default=False)
    reason: Mapped[str] = mapped_column(Text, default="")
    plan_ref: Mapped[str | None] = mapped_column(String(120), default=None)
    config: Mapped[dict[str, Any]] = mapped_column(default=dict)
    created_at: Mapped[datetime] = created_at_col()


class Document(Base):
    """Any retrieved content used as a snapshot or as evidence (live, archived, or search)."""

    __tablename__ = "documents"
    __table_args__ = (Index("ix_documents_ws_url", "workspace_id", "url"),)
    id: Mapped[uuid.UUID] = uuid_pk()
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"))
    url: Mapped[str] = mapped_column(Text)
    final_url: Mapped[str | None] = mapped_column(Text, default=None)
    publisher: Mapped[str] = mapped_column(String(255), default="")
    title: Mapped[str | None] = mapped_column(Text, default=None)
    content_type: Mapped[str | None] = mapped_column(String(120), default=None)
    content_hash: Mapped[str] = mapped_column(String(64), default="")
    text: Mapped[str] = mapped_column(Text, default="")
    blocks: Mapped[list[Any]] = mapped_column(default=list)
    word_count: Mapped[int] = mapped_column(Integer, default=0)
    quality: Mapped[str] = mapped_column(String(16), default="ok")
    quality_reason: Mapped[str | None] = mapped_column(Text, default=None)
    published_at: Mapped[datetime | None] = mapped_column(default=None)
    fetched_at: Mapped[datetime] = mapped_column(default=utcnow)
    origin: Mapped[str] = mapped_column(String(16), default="live")  # live | archive | sandbox | search
    archive_timestamp: Mapped[str | None] = mapped_column(String(14), default=None)
    meta: Mapped[dict[str, Any]] = mapped_column(default=dict)


class SourceSnapshot(Base):
    __tablename__ = "source_snapshots"
    __table_args__ = (Index("ix_snapshots_source_time", "source_id", "observed_at"),)
    id: Mapped[uuid.UUID] = uuid_pk()
    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"))
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    observed_at: Mapped[datetime] = mapped_column(default=utcnow)
    is_baseline: Mapped[bool] = mapped_column(Boolean, default=False)
    origin: Mapped[str] = mapped_column(String(16), default="live")
    quality: Mapped[str] = mapped_column(String(16), default="ok")
    created_at: Mapped[datetime] = created_at_col()


class SourceCheck(Base):
    """One scheduled or manual check of a source — the base of the attention funnel."""

    __tablename__ = "source_checks"
    __table_args__ = (Index("ix_source_checks_ws_time", "workspace_id", "started_at"),)
    id: Mapped[uuid.UUID] = uuid_pk()
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"))
    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"), index=True)
    started_at: Mapped[datetime] = mapped_column(default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(default=None)
    outcome: Mapped[str] = mapped_column(String(32), default="error")
    http_status: Mapped[int | None] = mapped_column(Integer, default=None)
    new_items: Mapped[int] = mapped_column(Integer, default=0)
    changes: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, default=None)
    snapshot_id: Mapped[uuid.UUID | None] = mapped_column(default=None)


class SandboxPage(Base):
    """Fictional pages for demonstrating change detection on demand (``sandbox://slug``)."""

    __tablename__ = "sandbox_pages"
    slug: Mapped[str] = mapped_column(String(120), primary_key=True)
    title: Mapped[str] = mapped_column(String(300))
    html: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


# ---------------------------------------------------------------------------------------
# World state: facts and their versions
# ---------------------------------------------------------------------------------------


class Fact(Base):
    """A tracked attribute of an entity, e.g. Razorpay → pricing.standard_domestic_fee."""

    __tablename__ = "facts"
    __table_args__ = (UniqueConstraint("entity_id", "key"),)
    id: Mapped[uuid.UUID] = uuid_pk()
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    entity_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("entities.id", ondelete="CASCADE"))
    area: Mapped[str] = mapped_column(String(80))
    key: Mapped[str] = mapped_column(String(200))
    label: Mapped[str] = mapped_column(String(300))
    value_type: Mapped[str] = mapped_column(String(20), default="text")
    hint: Mapped[str] = mapped_column(Text, default="")
    source_refs: Mapped[list[str]] = mapped_column(default=list)
    current_version_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    first_seen_at: Mapped[datetime | None] = mapped_column(default=None)
    last_changed_at: Mapped[datetime | None] = mapped_column(default=None)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = created_at_col()


class StateVersion(Base):
    """One immutable value of a fact over time (spec review C9: observed vs effective)."""

    __tablename__ = "state_versions"
    __table_args__ = (Index("ix_state_versions_fact_time", "fact_id", "observed_at"),)
    id: Mapped[uuid.UUID] = uuid_pk()
    fact_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("facts.id", ondelete="CASCADE"))
    value: Mapped[dict[str, Any]] = mapped_column(default=dict)
    value_display: Mapped[str] = mapped_column(Text)
    value_key: Mapped[str] = mapped_column(String(64))  # hash of the normalised value for comparisons
    valid_from: Mapped[datetime | None] = mapped_column(default=None)
    observed_at: Mapped[datetime] = mapped_column(default=utcnow)
    observed_via: Mapped[str] = mapped_column(String(16), default="live")  # live | archive | news | user
    source_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    document_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    event_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    evidence_status: Mapped[str] = mapped_column(String(24), default="unverified")
    quote: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = created_at_col()


# ---------------------------------------------------------------------------------------
# Change: events, claims, evidence, investigations
# ---------------------------------------------------------------------------------------


class Event(Base):
    """A detected (potential) change. Only some become intelligence reports."""

    __tablename__ = "events"
    __table_args__ = (
        Index("ix_events_ws_status", "workspace_id", "status"),
        Index("ix_events_ws_cluster", "workspace_id", "cluster_key"),
        Index("ix_events_ws_detected", "workspace_id", "detected_at"),
    )
    id: Mapped[uuid.UUID] = uuid_pk()
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"))
    entity_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("entities.id", ondelete="SET NULL"), default=None)
    fact_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    source_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    area: Mapped[str] = mapped_column(String(80), default="general")
    event_type: Mapped[str] = mapped_column(String(40), default="other")
    title: Mapped[str] = mapped_column(Text)
    summary: Mapped[str] = mapped_column(Text, default="")
    before_display: Mapped[str | None] = mapped_column(Text, default=None)
    after_display: Mapped[str | None] = mapped_column(Text, default=None)
    detected_at: Mapped[datetime] = mapped_column(default=utcnow)
    occurred_at: Mapped[datetime | None] = mapped_column(default=None)
    detection_source: Mapped[str] = mapped_column(String(24), default="page_diff")
    snapshot_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    document_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    diff_excerpt: Mapped[str | None] = mapped_column(Text, default=None)
    cluster_key: Mapped[str | None] = mapped_column(String(300), default=None)
    status: Mapped[str] = mapped_column(String(24), default="candidate")
    materiality: Mapped[str] = mapped_column(String(16), default="none")
    materiality_reason: Mapped[str | None] = mapped_column(Text, default=None)
    filter_tier: Mapped[int | None] = mapped_column(Integer, default=None)
    filter_reason: Mapped[str | None] = mapped_column(Text, default=None)
    evidence_status: Mapped[str] = mapped_column(String(24), default="unverified")
    severity: Mapped[str | None] = mapped_column(String(16), default=None)
    is_historical: Mapped[bool] = mapped_column(Boolean, default=False)
    details: Mapped[dict[str, Any]] = mapped_column(default=dict)
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


class Claim(Base):
    """A checkable statement about the world, e.g. "Razorpay's standard fee is now 1.8%"."""

    __tablename__ = "claims"
    id: Mapped[uuid.UUID] = uuid_pk()
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), index=True)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    statement: Mapped[str] = mapped_column(Text)
    claim_type: Mapped[str] = mapped_column(String(24), default="occurrence")
    evidence_status: Mapped[str] = mapped_column(String(24), default="unverified")
    created_by: Mapped[str] = mapped_column(String(24), default="pipeline")
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


class Evidence(Base):
    """A quoted, attributable piece of support or contradiction for a claim (spec review C4)."""

    __tablename__ = "evidence"
    id: Mapped[uuid.UUID] = uuid_pk()
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    claim_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("claims.id", ondelete="CASCADE"), index=True)
    url: Mapped[str] = mapped_column(Text)
    title: Mapped[str | None] = mapped_column(Text, default=None)
    publisher: Mapped[str] = mapped_column(String(255), default="")
    source_class: Mapped[str] = mapped_column(String(16), default="independent")
    is_archive: Mapped[bool] = mapped_column(Boolean, default=False)
    stance: Mapped[str] = mapped_column(String(16), default="supports")
    quote: Mapped[str] = mapped_column(Text, default="")
    quote_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    document_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    published_at: Mapped[datetime | None] = mapped_column(default=None)
    retrieved_at: Mapped[datetime] = mapped_column(default=utcnow)
    added_by: Mapped[str] = mapped_column(String(16), default="pipeline")
    run_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    note: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = created_at_col()


class Investigation(Base):
    __tablename__ = "investigations"
    id: Mapped[uuid.UUID] = uuid_pk()
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), index=True)
    run_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    status: Mapped[str] = mapped_column(String(24), default="running")
    evidence_status: Mapped[str | None] = mapped_column(String(24), default=None)
    conclusion: Mapped[dict[str, Any]] = mapped_column(default=dict)
    started_at: Mapped[datetime] = mapped_column(default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(default=None)


# ---------------------------------------------------------------------------------------
# Intelligence and delivery
# ---------------------------------------------------------------------------------------


class IntelligenceReport(Base):
    """The intelligence card: facts, agent assessment, evidence status, routing."""

    __tablename__ = "intelligence_reports"
    __table_args__ = (Index("ix_reports_ws_detected", "workspace_id", "detected_at"),)
    id: Mapped[uuid.UUID] = uuid_pk()
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"))
    event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), unique=True)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    area: Mapped[str] = mapped_column(String(80))
    title: Mapped[str] = mapped_column(Text)
    change_label: Mapped[str] = mapped_column(String(120))
    what_changed: Mapped[str] = mapped_column(Text)
    why_it_matters: Mapped[str] = mapped_column(Text)
    considerations: Mapped[list[str]] = mapped_column(default=list)
    assumptions: Mapped[list[str]] = mapped_column(default=list)
    watch_next: Mapped[list[str]] = mapped_column(default=list)
    affected_team_ids: Mapped[list[str]] = mapped_column(default=list)
    severity: Mapped[str] = mapped_column(String(16))
    severity_rationale: Mapped[str] = mapped_column(Text, default="")
    evidence_status: Mapped[str] = mapped_column(String(24))
    evidence_summary: Mapped[str] = mapped_column(Text, default="")
    previous_state: Mapped[str | None] = mapped_column(Text, default=None)
    current_state: Mapped[str | None] = mapped_column(Text, default=None)
    detected_at: Mapped[datetime] = mapped_column(default=utcnow)
    occurred_at: Mapped[datetime | None] = mapped_column(default=None)
    is_historical: Mapped[bool] = mapped_column(Boolean, default=False)
    analysis_run_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    status: Mapped[str] = mapped_column(String(16), default="published")
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


class ReportRead(Base):
    __tablename__ = "report_reads"
    report_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("intelligence_reports.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    read_at: Mapped[datetime] = mapped_column(default=utcnow)


class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[uuid.UUID] = uuid_pk()
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    report_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("intelligence_reports.id", ondelete="CASCADE"))
    team_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    channel: Mapped[str] = mapped_column(String(16), default="inbox")
    status: Mapped[str] = mapped_column(String(16), default="pending")
    error: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = created_at_col()
    sent_at: Mapped[datetime | None] = mapped_column(default=None)
    read_at: Mapped[datetime | None] = mapped_column(default=None)


class UserFeedback(Base):
    __tablename__ = "user_feedback"
    id: Mapped[uuid.UUID] = uuid_pk()
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    report_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("intelligence_reports.id", ondelete="CASCADE"))
    user_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    verdict: Mapped[str] = mapped_column(String(16))
    reason: Mapped[str] = mapped_column(String(24))
    note: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = created_at_col()


class Approval(Base):
    """A consequential action waiting for a human decision (spec §16)."""

    __tablename__ = "approvals"
    id: Mapped[uuid.UUID] = uuid_pk()
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    report_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    action_type: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict[str, Any]] = mapped_column(default=dict)
    reason: Mapped[str] = mapped_column(Text, default="")
    requested_by: Mapped[str] = mapped_column(String(40), default="user")
    # The person who asked for the action; they may not approve it themselves.
    requested_by_user_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    decided_by: Mapped[str | None] = mapped_column(String(320), default=None)
    decided_at: Mapped[datetime | None] = mapped_column(default=None)
    decision_note: Mapped[str | None] = mapped_column(Text, default=None)
    executed_at: Mapped[datetime | None] = mapped_column(default=None)
    result: Mapped[dict[str, Any] | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = created_at_col()


# ---------------------------------------------------------------------------------------
# Agent runtime audit trail
# ---------------------------------------------------------------------------------------


class AgentRun(Base):
    """One execution of an agent, with its budget and usage. Steps are the full trace."""

    __tablename__ = "agent_runs"
    __table_args__ = (Index("ix_agent_runs_ws_created", "workspace_id", "created_at"),)
    id: Mapped[uuid.UUID] = uuid_pk()
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"))
    agent: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(24), default="running")
    task: Mapped[dict[str, Any]] = mapped_column(default=dict)
    budget: Mapped[dict[str, Any]] = mapped_column(default=dict)
    usage: Mapped[dict[str, Any]] = mapped_column(default=dict)
    result: Mapped[dict[str, Any] | None] = mapped_column(default=None)
    error: Mapped[str | None] = mapped_column(Text, default=None)
    subject_type: Mapped[str | None] = mapped_column(String(24), default=None)
    subject_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    parent_run_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    started_at: Mapped[datetime | None] = mapped_column(default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = created_at_col()


class RunStep(Base):
    __tablename__ = "run_steps"
    __table_args__ = (UniqueConstraint("run_id", "idx"),)
    id: Mapped[uuid.UUID] = uuid_pk()
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agent_runs.id", ondelete="CASCADE"))
    idx: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(24))
    name: Mapped[str | None] = mapped_column(String(120), default=None)
    summary: Mapped[str] = mapped_column(Text, default="")
    input: Mapped[dict[str, Any] | None] = mapped_column(default=None)
    output: Mapped[dict[str, Any] | None] = mapped_column(default=None)
    tokens_in: Mapped[int | None] = mapped_column(Integer, default=None)
    tokens_out: Mapped[int | None] = mapped_column(Integer, default=None)
    latency_ms: Mapped[int | None] = mapped_column(Integer, default=None)
    created_at: Mapped[datetime] = created_at_col()


# ---------------------------------------------------------------------------------------
# Background execution
# ---------------------------------------------------------------------------------------


class Job(Base):
    """Postgres-backed job queue row (spec review C14).

    Jobs are inserted in the same transaction as the state change that causes them, and
    claimed with ``FOR UPDATE SKIP LOCKED``. ``dedupe_key`` is unique among live jobs.
    """

    __tablename__ = "jobs"
    __table_args__ = (
        Index("ix_jobs_claim", "status", "priority", "run_at"),
        Index(
            "uq_jobs_live_dedupe",
            "dedupe_key",
            unique=True,
            postgresql_where=text("status IN ('queued', 'running')"),
        ),
    )
    id: Mapped[uuid.UUID] = uuid_pk()
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(default=None, index=True)
    kind: Mapped[str] = mapped_column(String(40))
    payload: Mapped[dict[str, Any]] = mapped_column(default=dict)
    status: Mapped[str] = mapped_column(String(16), default="queued")
    priority: Mapped[int] = mapped_column(Integer, default=100)
    run_at: Mapped[datetime] = mapped_column(default=utcnow)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    locked_by: Mapped[str | None] = mapped_column(String(120), default=None)
    locked_at: Mapped[datetime | None] = mapped_column(default=None)
    last_error: Mapped[str | None] = mapped_column(Text, default=None)
    dedupe_key: Mapped[str | None] = mapped_column(String(300), default=None)
    result: Mapped[dict[str, Any] | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = created_at_col()
    finished_at: Mapped[datetime | None] = mapped_column(default=None)


class WorkerHeartbeat(Base):
    __tablename__ = "worker_heartbeats"
    worker_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    seen_at: Mapped[datetime] = mapped_column(default=utcnow)
    info: Mapped[dict[str, Any]] = mapped_column(default=dict)


__all__ = [
    "AgentRun",
    "Approval",
    "Claim",
    "Document",
    "Entity",
    "EntityRelationship",
    "Event",
    "Evidence",
    "Fact",
    "IntelligenceReport",
    "Investigation",
    "Job",
    "LearnedRule",
    "MonitoringPolicy",
    "Notification",
    "Organization",
    "ReportRead",
    "RunStep",
    "SandboxPage",
    "Source",
    "SourceCheck",
    "SourceSnapshot",
    "StateVersion",
    "Team",
    "User",
    "UserFeedback",
    "Workspace",
    "WorkspaceMember",
    "WorkerHeartbeat",
]


class AgentBrief(Base):
    """A one-shot intelligence brief requested through the hosted agent endpoint (aiKart method 2).

    Not tenant-owned: briefs are produced for API callers and only readable by their id.
    """

    __tablename__ = "agent_briefs"
    __table_args__ = (Index("ix_agent_briefs_created", "created_at"),)
    id: Mapped[uuid.UUID] = uuid_pk()
    status: Mapped[str] = mapped_column(String(16), default="queued")  # queued|running|succeeded|failed
    input: Mapped[dict[str, Any]] = mapped_column(default=dict)
    markdown: Mapped[str | None] = mapped_column(Text, default=None)
    result: Mapped[dict[str, Any] | None] = mapped_column(default=None)
    trace: Mapped[list[Any]] = mapped_column(default=list)
    error: Mapped[str | None] = mapped_column(Text, default=None)
    client: Mapped[str | None] = mapped_column(String(120), default=None)
    created_at: Mapped[datetime] = created_at_col()
    finished_at: Mapped[datetime | None] = mapped_column(default=None)
