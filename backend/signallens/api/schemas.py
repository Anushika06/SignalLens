"""API response/request models — a transcription of docs/api-contract.md."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import AfterValidator, AliasChoices, BaseModel, Field

from signallens.notify.email import normalize_emails
from signallens.plan import MonitoringPlan

Severity = Literal["critical", "high", "medium", "low"]
EvidenceStatus = Literal["confirmed", "corroborated", "single_source", "conflicting", "unverified"]
Materiality = Literal["none", "low", "medium", "high", "critical"]
Importance = Literal["critical", "high", "medium", "low"]


# --- auth ---------------------------------------------------------------------------------
class SignupIn(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=8, max_length=200)
    name: str = Field(min_length=1, max_length=200)
    org_name: str = Field(min_length=1, max_length=200)


class LoginIn(BaseModel):
    email: str
    password: str


class UserOut(BaseModel):
    id: str
    email: str
    name: str


class OrgOut(BaseModel):
    id: str
    name: str


class Me(BaseModel):
    user: UserOut
    org: OrgOut


# --- system -------------------------------------------------------------------------------
class Health(BaseModel):
    ok: bool
    db: bool
    worker_seen_at: datetime | None


class LLMConfig(BaseModel):
    provider: str | None
    fast_model: str | None
    reasoning_model: str | None
    configured: bool


class SearchConfig(BaseModel):
    provider: str | None
    configured: bool


class EmailConfig(BaseModel):
    provider: str | None  # "brevo" | "resend" | "smtp" | None
    configured: bool
    sender: str | None  # From address (never a key)
    digest_enabled: bool
    reason: str | None = None  # why email is not configured


class SystemConfig(BaseModel):
    llm: LLMConfig
    search: SearchConfig
    email: EmailConfig | None = None
    sandbox_enabled: bool
    demo_login: bool
    version: str


# --- workspaces ---------------------------------------------------------------------------
class CompanyProfile(BaseModel):
    company_name: str = ""
    website: str | None = None
    description: str = ""
    products: list[str] = Field(default_factory=list)
    markets: list[str] = Field(default_factory=list)
    competitors: list[str] = Field(default_factory=list)
    relationship_to_subjects: str = ""


# Validated, trimmed, de-duplicated recipient addresses (422 on an invalid one).
TeamEmails = Annotated[list[str], AfterValidator(normalize_emails)]


class TeamInput(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    areas: list[str] = Field(default_factory=list)
    members: list[str] = Field(default_factory=list)
    slack_webhook_url: str | None = None
    # Recipients of the team's email digest and immediate email alerts.
    emails: TeamEmails = Field(default_factory=list)


class TeamPatch(BaseModel):
    name: str | None = None
    areas: list[str] | None = None
    members: list[str] | None = None
    slack_webhook_url: str | None = None
    emails: TeamEmails | None = None


class Team(BaseModel):
    id: str
    name: str
    areas: list[str]
    members: list[str]
    slack_configured: bool
    emails: list[str] = Field(default_factory=list)


class EmailTestResult(BaseModel):
    delivered: bool
    provider: str | None  # "brevo" | "resend" | "smtp" | None (not configured)
    recipients: list[str]
    message_id: str | None = None
    error: str | None = None


class WorkspaceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    profile: CompanyProfile | None = None
    teams: list[TeamInput] | None = None


class WorkspacePatch(BaseModel):
    name: str | None = None
    profile: CompanyProfile | None = None


class WorkspaceSummary(BaseModel):
    id: str
    name: str
    status: str
    created_at: datetime
    subjects: list[str]
    unread_reports: int


class WorkspaceDetail(WorkspaceSummary):
    profile: CompanyProfile
    teams: list[Team]
    active_policy_id: str | None
    pending_policy_id: str | None
    last_seen_at: datetime | None
    # The signed-in user's role here: owner | admin | member. Owners and admins approve.
    my_role: str = "member"
    can_approve: bool = False
    can_manage_members: bool = False


class SeenOut(BaseModel):
    previous_seen_at: datetime | None
    seen_at: datetime


# --- plans --------------------------------------------------------------------------------
class PlanCreate(BaseModel):
    request_text: str = Field(min_length=3, max_length=4000)


class PlanSpecIn(BaseModel):
    spec: MonitoringPlan


class ApproveIn(BaseModel):
    spec: MonitoringPlan | None = None


class PlanDetail(BaseModel):
    id: str
    version: int
    status: str
    request_text: str
    run_id: str | None
    spec: MonitoringPlan | None
    error: str | None
    created_at: datetime
    approved_at: datetime | None


class ApproveResult(BaseModel):
    policy_id: str
    status: Literal["active"]
    sources_created: int
    jobs_enqueued: int


# --- overview / activity --------------------------------------------------------------------
class EntityRef(BaseModel):
    id: str
    name: str


class FeedbackRef(BaseModel):
    verdict: str
    reason: str


class ReportSummary(BaseModel):
    id: str
    title: str
    change_label: str
    area: str
    area_label: str
    entity: EntityRef | None
    event_type: str
    severity: Severity
    evidence_status: EvidenceStatus
    previous_state: str | None
    current_state: str | None
    detected_at: datetime
    occurred_at: datetime | None
    is_historical: bool
    unread: bool
    feedback: FeedbackRef | None


class SubjectCard(BaseModel):
    entity_id: str
    name: str
    kind: str
    role: str
    areas: list[str]
    facts_count: int
    reports_30d: int
    last_change_at: datetime | None


class Funnel(BaseModel):
    window_days: int
    checks: int
    changes: int
    filtered: int
    material: int
    investigated: int
    published: int


class ActivityLink(BaseModel):
    type: Literal["report", "run", "source", "event", "plan"]
    id: str


class ActivityItem(BaseModel):
    id: str
    at: datetime
    kind: str
    message: str
    status: Literal["info", "running", "success", "warning", "error"]
    link: ActivityLink | None


class AreaView(BaseModel):
    key: str
    label: str
    importance: Importance
    effective_importance: Importance


class SourcesHealth(BaseModel):
    total: int
    active: int
    failing: int
    next_check_at: datetime | None


class Overview(BaseModel):
    workspace: WorkspaceSummary
    last_seen_at: datetime | None
    subjects: list[SubjectCard]
    areas: list[AreaView]
    funnel: Funnel
    recent_reports: list[ReportSummary]
    historical_count: int
    activity: list[ActivityItem]
    pending_approvals: int
    sources: SourcesHealth


# --- reports ------------------------------------------------------------------------------
class EvidenceOut(BaseModel):
    id: str
    url: str
    title: str | None
    publisher: str
    source_class: str
    is_archive: bool
    stance: str
    quote: str
    quote_verified: bool
    published_at: datetime | None
    retrieved_at: datetime
    added_by: str


class StateVersionOut(BaseModel):
    id: str
    value_display: str
    valid_from: datetime | None
    observed_at: datetime
    observed_via: str
    evidence_status: str
    source_url: str | None
    event_id: str | None


class FactWithHistory(BaseModel):
    id: str
    key: str
    label: str
    history: list[StateVersionOut]


class EventView(BaseModel):
    id: str
    status: str
    detection_source: str
    materiality: str
    materiality_reason: str | None
    source_url: str | None
    diff_excerpt: str | None


class InvestigationView(BaseModel):
    run_id: str
    status: str
    steps: int
    tool_calls: int
    duration_ms: int | None
    conclusion: str | None


class Approval(BaseModel):
    id: str
    action_type: str
    title: str
    payload: dict[str, Any]
    reason: str
    requested_by: str
    report_id: str | None
    status: str
    created_at: datetime
    decided_at: datetime | None
    decided_by: str | None
    decision_note: str | None = None
    result: dict[str, Any] | None
    # Who asked for it (None = proposed by an agent) and whether the viewer may decide it.
    requested_by_user_id: str | None = None
    requested_by_name: str | None = None
    can_decide: bool = False
    cannot_decide_reason: str | None = None


class ReportDetail(ReportSummary):
    what_changed: str
    why_it_matters: str
    considerations: list[str]
    assumptions: list[str]
    watch_next: list[str]
    affected_teams: list[EntityRef]
    evidence_summary: str
    evidence: list[EvidenceOut]
    fact: FactWithHistory | None
    event: EventView
    investigation: InvestigationView | None
    analysis_run_id: str | None
    approvals: list[Approval]
    related: list[ReportSummary]


class FeedbackIn(BaseModel):
    verdict: Literal["relevant", "not_relevant"]
    reason: Literal["useful", "always_urgent", "too_minor", "not_our_area", "wrong_entity", "inaccurate",
                    "already_known", "duplicate", "other"]
    note: str | None = Field(None, max_length=2000)


class FeedbackOut(BaseModel):
    id: str
    verdict: str
    reason: str
    note: str | None
    created_at: datetime


class LearnedRuleOut(BaseModel):
    id: str
    kind: str
    explanation: str
    scope: dict[str, str]
    effect: dict[str, str]
    evidence_count: int
    active: bool
    created_at: datetime
    revoked_at: datetime | None


class FeedbackResult(BaseModel):
    feedback: FeedbackOut
    learned_rules: list[LearnedRuleOut]
    message: str


class ShareIn(BaseModel):
    to: str = Field(min_length=3, max_length=320, validation_alias=AliasChoices("to", "recipient"))
    note: str | None = Field(None, max_length=4000)


# --- world ---------------------------------------------------------------------------------
class EntitySummary(BaseModel):
    id: str
    name: str
    kind: str
    role: str
    aliases: list[str]
    official_domains: list[str]
    description: str
    facts_count: int
    reports_count: int
    last_change_at: datetime | None


class FactSummary(BaseModel):
    id: str
    key: str
    label: str
    area: str
    value_type: str
    current: StateVersionOut | None
    versions: int
    last_changed_at: datetime | None


class EntityKindRef(BaseModel):
    id: str
    name: str
    kind: str


class RelationshipOut(BaseModel):
    id: str
    predicate: str
    direction: Literal["out", "in"]
    other: EntityKindRef
    first_seen_at: datetime
    last_seen_at: datetime


class TimelineItem(BaseModel):
    report_id: str | None
    event_id: str
    title: str
    area: str
    event_type: str
    severity: str | None
    evidence_status: str
    occurred_at: datetime | None
    detected_at: datetime
    is_historical: bool


class EntityDetail(BaseModel):
    entity: EntitySummary
    facts: list[FactSummary]
    relationships: list[RelationshipOut]
    timeline: list[TimelineItem]


class FactDetail(BaseModel):
    fact: FactSummary
    entity: EntityRef
    versions: list[StateVersionOut]


# --- monitoring ----------------------------------------------------------------------------
class PolicyArea(BaseModel):
    key: str
    label: str
    importance: Importance
    effective_importance: Importance
    threshold: Materiality
    route_to: list[str]


class PolicyView(BaseModel):
    id: str
    version: int
    status: str
    approved_at: datetime | None
    request_text: str
    summary: str
    areas: list[PolicyArea]
    spec: MonitoringPlan


class SourceView(BaseModel):
    id: str
    kind: str
    url: str | None
    query: str | None
    entity: EntityRef | None
    areas: list[str]
    authority: str
    priority: str
    check_every_hours: float
    current_interval_hours: float
    next_check_at: datetime | None
    last_checked_at: datetime | None
    last_changed_at: datetime | None
    last_outcome: str | None
    consecutive_failures: int
    active: bool
    reason: str
    snapshots: int
    backfill: bool


class SourcePatch(BaseModel):
    active: bool | None = None
    check_every_hours: float | None = Field(None, ge=0.25, le=720)
    priority: Literal["high", "medium", "low"] | None = None


class SourceCheckOut(BaseModel):
    id: str
    started_at: datetime
    finished_at: datetime | None
    outcome: str
    http_status: int | None
    new_items: int
    changes: int
    error: str | None


class JobRef(BaseModel):
    job_id: str


class FilteredChange(BaseModel):
    id: str
    title: str
    area: str
    entity: EntityRef | None
    detected_at: datetime
    materiality: str
    filter_reason: str
    detection_source: str
    source_url: str | None
    tier: int


# --- runs --------------------------------------------------------------------------------
class UsageOut(BaseModel):
    llm_calls: int = 0
    tool_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    est_cost_usd: float = 0.0


class SubjectRef(BaseModel):
    type: str
    id: str


class RunSummary(BaseModel):
    id: str
    agent: str
    status: str
    title: str
    subject: SubjectRef | None
    started_at: datetime | None
    finished_at: datetime | None
    usage: UsageOut


class BudgetOut(BaseModel):
    max_steps: int
    max_tool_calls: int
    max_seconds: float
    max_cost_usd: float


class RunStepOut(BaseModel):
    idx: int
    kind: str
    name: str | None
    summary: str
    input: Any
    output: Any
    tokens_in: int | None
    tokens_out: int | None
    latency_ms: int | None
    created_at: datetime


class RunDetail(RunSummary):
    task: dict[str, Any]
    budget: BudgetOut
    result: dict[str, Any] | None
    error: str | None
    steps: list[RunStepOut]


# --- approvals / notifications / sandbox ----------------------------------------------------
class DecideIn(BaseModel):
    decision: Literal["approve", "reject"]
    note: str | None = None


class NotificationItem(BaseModel):
    id: str
    report_id: str
    title: str
    severity: str
    team: str | None
    channel: str
    status: str
    created_at: datetime
    read_at: datetime | None


class SandboxPageOut(BaseModel):
    slug: str
    title: str
    html: str
    updated_at: datetime


class SandboxPageIn(BaseModel):
    title: str | None = None
    html: str = Field(max_length=500_000)


# --- single sign-on and workspace members ---------------------------------------------------
class SsoConfig(BaseModel):
    enabled: bool
    provider_name: str


WorkspaceRole = Literal["owner", "admin", "member"]


class Member(BaseModel):
    user_id: str
    name: str
    email: str
    role: str
    auth_provider: str
    is_you: bool
    joined_at: datetime


class MemberAdd(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    role: WorkspaceRole = "member"
    name: str | None = Field(default=None, max_length=200)


class MemberPatch(BaseModel):
    role: WorkspaceRole
