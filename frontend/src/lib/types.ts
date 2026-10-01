/**
 * SignalLens API types — transcribed from docs/api-contract.md (v1).
 *
 * The contract is the source of truth. Section numbers below match the contract so a reader
 * can cross-check field by field. Types that the contract implies but does not name (request
 * bodies, small responses) are grouped at the end under "Request / response helpers".
 */

// ---------------------------------------------------------------------------------------------
// 1. Shared enums
// ---------------------------------------------------------------------------------------------

export type Severity = "critical" | "high" | "medium" | "low";
export type EvidenceStatus = "confirmed" | "corroborated" | "single_source" | "conflicting" | "unverified";
export type Materiality = "none" | "low" | "medium" | "high" | "critical";
export type Importance = "critical" | "high" | "medium" | "low";
export type EntityKind = "company" | "product" | "regulator" | "person" | "organization" | "topic";
export type EntityRole = "subject" | "competitor" | "regulator" | "partner" | "us" | "related";
export type SourceKind = "page" | "news";
export type Authority = "official" | "regulator" | "independent" | "community";
export type SourceClass = "primary" | "independent" | "community";
export type Stance = "supports" | "contradicts" | "context";
export type EventStatus =
  | "candidate"
  | "filtered"
  | "investigating"
  | "analyzing"
  | "published"
  | "dismissed"
  | "historical"
  | "failed";
export type EventType =
  | "value_change"
  | "item_added"
  | "item_removed"
  | "content_change"
  | "product_launch"
  | "pricing"
  | "partnership"
  | "funding"
  | "leadership"
  | "regulatory"
  | "legal"
  | "acquisition"
  | "financials"
  | "expansion"
  | "other";
export type DetectionSource = "page_diff" | "attribute" | "news" | "backfill" | "manual";
export type WorkspaceStatus = "setup" | "planning" | "awaiting_approval" | "baselining" | "monitoring" | "paused";
export type PolicyStatus = "planning" | "pending_approval" | "active" | "superseded" | "rejected" | "failed";
export type RunStatus = "queued" | "running" | "succeeded" | "failed" | "budget_exhausted";
export type AgentName = "planner" | "investigator" | "impact_analyst" | "extractor" | "triage" | "materiality";
export type StepKind =
  | "decision"
  | "tool_call"
  | "observation"
  | "guardrail"
  | "llm_call"
  | "note"
  | "state_update"
  | "error";
export type FeedbackVerdict = "relevant" | "not_relevant";
export type FeedbackReason =
  | "useful"
  | "always_urgent"
  | "too_minor"
  | "not_our_area"
  | "wrong_entity"
  | "inaccurate"
  | "already_known"
  | "duplicate"
  | "other";
export type LearnedRuleKind = "materiality_threshold" | "area_importance" | "publisher_trust" | "entity_exclusion";
export type ApprovalStatus = "pending" | "approved" | "rejected" | "executed" | "failed";
export type ApprovalActionType = "send_external_email" | "share_report_externally" | "post_external_webhook";
export type CheckOutcome =
  | "baseline"
  | "unchanged"
  | "not_modified"
  | "changed"
  | "new_items"
  | "no_new_items"
  | "degenerate"
  | "blocked"
  | "error";
export type ActivityKind =
  | "plan"
  | "baseline"
  | "backfill"
  | "check"
  | "change"
  | "filtered"
  | "investigation"
  | "report"
  | "notification"
  | "approval"
  | "error";

// ---------------------------------------------------------------------------------------------
// 2. Auth
// ---------------------------------------------------------------------------------------------

export type Me = {
  user: { id: string; email: string; name: string };
  org: { id: string; name: string };
};

// ---------------------------------------------------------------------------------------------
// 3. System
// ---------------------------------------------------------------------------------------------

export type Health = { ok: boolean; db: boolean; worker_seen_at: string | null };

export type SystemConfig = {
  llm: { provider: string | null; fast_model: string | null; reasoning_model: string | null; configured: boolean };
  search: { provider: string | null; configured: boolean };
  /** Demo lab pages available. */
  sandbox_enabled: boolean;
  /** Show the demo-account shortcut on sign-in (off in production by default). */
  demo_login?: boolean;
  version: string;
};

// ---------------------------------------------------------------------------------------------
// 4. Workspaces, profile, teams
// ---------------------------------------------------------------------------------------------

/** "Us" — used by impact analysis and routing. */
export type CompanyProfile = {
  /** "" allowed (profile optional). */
  company_name: string;
  website: string | null;
  /** What we do, for whom. */
  description: string;
  products: string[];
  /** e.g. ["India", "SMB merchants"] */
  markets: string[];
  /** Names the user already knows. */
  competitors: string[];
  /** Free text, e.g. "Razorpay is our main competitor". */
  relationship_to_subjects: string;
};

export type WorkspaceSummary = {
  id: string;
  name: string;
  status: WorkspaceStatus;
  created_at: string;
  /** Names of subject entities. */
  subjects: string[];
  unread_reports: number;
};

export type WorkspaceDetail = WorkspaceSummary & {
  profile: CompanyProfile;
  teams: Team[];
  active_policy_id: string | null;
  /** Plan being prepared or awaiting approval. */
  pending_policy_id: string | null;
  /** For the current user. */
  last_seen_at: string | null;
};

export type TeamInput = { name: string; areas: string[]; members: string[]; slack_webhook_url?: string | null };

export type Team = { id: string; name: string; areas: string[]; members: string[]; slack_configured: boolean };

// ---------------------------------------------------------------------------------------------
// 5. Monitoring plans (onboarding + human approval)
// ---------------------------------------------------------------------------------------------

export type PlanDetail = {
  id: string;
  version: number;
  status: PolicyStatus;
  request_text: string;
  /** Planner run — show its steps live while planning. */
  run_id: string | null;
  /** null while planning. */
  spec: MonitoringPlan | null;
  error: string | null;
  created_at: string;
  approved_at: string | null;
};

export type MonitoringPlan = {
  summary: string;
  domain: { industry: string; sector: string; geographies: string[]; rationale: string };
  entities: PlanEntity[];
  areas: PlanArea[];
  attributes: PlanAttribute[];
  sources: PlanSource[];
  open_questions: string[];
};

export type PlanEntity = {
  /** Stable key within the plan, e.g. "razorpay". */
  ref: string;
  name: string;
  kind: EntityKind;
  role: EntityRole;
  aliases: string[];
  official_domains: string[];
  description: string;
  reason: string;
  enabled: boolean;
};

export type PlanArea = {
  /** e.g. "pricing" */
  key: string;
  /** e.g. "Pricing & fees" */
  label: string;
  description: string;
  importance: Importance;
  reason: string;
  /** Team names. */
  route_to: string[];
  enabled: boolean;
};

export type PlanAttributeValueType = "percent" | "money" | "number" | "text" | "list" | "date" | "boolean";

export type PlanAttribute = {
  /** e.g. "pricing.standard_domestic_fee" */
  key: string;
  entity_ref: string;
  area: string;
  label: string;
  value_type: PlanAttributeValueType;
  /** What exactly to extract. */
  hint: string;
  /** Which PlanSource.ref(s) contain it. */
  source_refs: string[];
  enabled: boolean;
};

export type Priority = "high" | "medium" | "low";

export type PlanSource = {
  ref: string;
  kind: SourceKind;
  /** For kind "page". */
  url: string | null;
  /** For kind "news". */
  query: string | null;
  entity_ref: string;
  areas: string[];
  authority: Authority;
  priority: Priority;
  check_every_hours: number;
  /** Replay web-archive history at baseline (pages only). */
  backfill: boolean;
  reason: string;
  enabled: boolean;
  validation: SourceValidation | null;
};

export type SourceValidation = {
  ok: boolean;
  http_status: number | null;
  robots_allowed: boolean | null;
  quality: "ok" | "degenerate" | "blocked" | null;
  title: string | null;
  note: string | null;
};

export type ApproveResult = { policy_id: string; status: "active"; sources_created: number; jobs_enqueued: number };

// ---------------------------------------------------------------------------------------------
// 6. Dashboard overview
// ---------------------------------------------------------------------------------------------

export type OverviewArea = { key: string; label: string; importance: Importance; effective_importance: Importance };

export type Overview = {
  workspace: WorkspaceSummary;
  last_seen_at: string | null;
  subjects: SubjectCard[];
  areas: OverviewArea[];
  funnel: Funnel;
  /** Newest first, max 12, excludes historical. */
  recent_reports: ReportSummary[];
  /** Backfilled historical reports available. */
  historical_count: number;
  /** Newest first, max 20. */
  activity: ActivityItem[];
  pending_approvals: number;
  sources: { total: number; active: number; failing: number; next_check_at: string | null };
};

export type SubjectCard = {
  entity_id: string;
  name: string;
  kind: EntityKind;
  role: EntityRole;
  areas: string[];
  facts_count: number;
  reports_30d: number;
  last_change_at: string | null;
};

/** Last `window_days` days (7 by default). */
export type Funnel = {
  window_days: number;
  checks: number;
  changes: number;
  filtered: number;
  material: number;
  investigated: number;
  published: number;
};

export type ActivityStatus = "info" | "running" | "success" | "warning" | "error";
export type ActivityLinkType = "report" | "run" | "source" | "event" | "plan";

export type ActivityItem = {
  id: string;
  at: string;
  kind: ActivityKind;
  message: string;
  status: ActivityStatus;
  link: { type: ActivityLinkType; id: string } | null;
};

// ---------------------------------------------------------------------------------------------
// 7. Intelligence reports (cards)
// ---------------------------------------------------------------------------------------------

export type EntityRef = { id: string; name: string };

export type ReportSummary = {
  id: string;
  /** e.g. "Razorpay introduces 0% platform fee for first 90 days" */
  title: string;
  /** e.g. "Pricing change", "New partnership" */
  change_label: string;
  area: string;
  area_label: string;
  entity: EntityRef | null;
  event_type: EventType;
  severity: Severity;
  evidence_status: EvidenceStatus;
  /** Display string, e.g. "2% flat". */
  previous_state: string | null;
  /** Display string, e.g. "0% for first 90 days, then 2%". */
  current_state: string | null;
  detected_at: string;
  occurred_at: string | null;
  is_historical: boolean;
  unread: boolean;
  feedback: { verdict: FeedbackVerdict; reason: FeedbackReason } | null;
};

export type ReportDetail = ReportSummary & {
  /** Facts only. */
  what_changed: string;
  /** Agent assessment (label it as such in the UI). */
  why_it_matters: string;
  considerations: string[];
  assumptions: string[];
  watch_next: string[];
  affected_teams: { id: string; name: string }[];
  /** e.g. "Confirmed — official pricing page; 2 independent reports" */
  evidence_summary: string;
  evidence: Evidence[];
  fact: { id: string; key: string; label: string; history: StateVersion[] } | null;
  event: {
    id: string;
    status: EventStatus;
    detection_source: DetectionSource;
    materiality: Materiality;
    materiality_reason: string | null;
    source_url: string | null;
    diff_excerpt: string | null;
  };
  investigation: {
    run_id: string;
    status: RunStatus;
    steps: number;
    tool_calls: number;
    duration_ms: number | null;
    conclusion: string | null;
  } | null;
  analysis_run_id: string | null;
  /** Proposed/decided external actions for this report. */
  approvals: Approval[];
  /** Same entity + area, max 5. */
  related: ReportSummary[];
};

export type Evidence = {
  id: string;
  url: string;
  title: string | null;
  publisher: string;
  source_class: SourceClass;
  is_archive: boolean;
  stance: Stance;
  quote: string;
  quote_verified: boolean;
  published_at: string | null;
  retrieved_at: string;
  added_by: "pipeline" | "agent" | "user";
};

export type ObservedVia = "live" | "archive" | "news" | "user";

export type StateVersion = {
  id: string;
  value_display: string;
  valid_from: string | null;
  observed_at: string;
  observed_via: ObservedVia;
  evidence_status: EvidenceStatus;
  source_url: string | null;
  event_id: string | null;
};

export type FeedbackInput = { verdict: FeedbackVerdict; reason: FeedbackReason; note?: string };

export type FeedbackResult = {
  feedback: {
    id: string;
    verdict: FeedbackVerdict;
    reason: FeedbackReason;
    note: string | null;
    created_at: string;
  };
  /** Rules created or strengthened by this feedback (may be empty). */
  learned_rules: LearnedRule[];
  /** Human sentence to show in a toast. */
  message: string;
};

// ---------------------------------------------------------------------------------------------
// 8. World state (entities, facts, timeline)
// ---------------------------------------------------------------------------------------------

export type EntitySummary = {
  id: string;
  name: string;
  kind: EntityKind;
  role: EntityRole;
  aliases: string[];
  official_domains: string[];
  description: string;
  facts_count: number;
  reports_count: number;
  last_change_at: string | null;
};

export type FactSummary = {
  id: string;
  key: string;
  label: string;
  area: string;
  value_type: string;
  current: StateVersion | null;
  versions: number;
  last_changed_at: string | null;
};

export type EntityRelationship = {
  id: string;
  predicate: string;
  direction: "out" | "in";
  other: { id: string; name: string; kind: EntityKind };
  first_seen_at: string;
  last_seen_at: string;
};

export type EntityTimelineItem = {
  report_id: string | null;
  event_id: string;
  title: string;
  area: string;
  event_type: EventType;
  severity: Severity | null;
  evidence_status: EvidenceStatus;
  occurred_at: string | null;
  detected_at: string;
  is_historical: boolean;
};

export type EntityDetail = {
  entity: EntitySummary;
  facts: FactSummary[];
  relationships: EntityRelationship[];
  timeline: EntityTimelineItem[];
};

export type FactDetail = { fact: FactSummary; entity: EntityRef; versions: StateVersion[] };

// ---------------------------------------------------------------------------------------------
// 9. Monitoring configuration, sources, learned rules, filtered changes
// ---------------------------------------------------------------------------------------------

export type PolicyArea = {
  key: string;
  label: string;
  importance: Importance;
  effective_importance: Importance;
  threshold: Materiality;
  route_to: string[];
};

export type PolicyView = {
  id: string;
  version: number;
  status: PolicyStatus;
  approved_at: string | null;
  request_text: string;
  summary: string;
  areas: PolicyArea[];
  spec: MonitoringPlan;
};

export type SourceView = {
  id: string;
  kind: SourceKind;
  url: string | null;
  query: string | null;
  entity: EntityRef | null;
  areas: string[];
  authority: Authority;
  priority: Priority;
  /** Configured base interval. */
  check_every_hours: number;
  /** Adaptive interval in use. */
  current_interval_hours: number;
  next_check_at: string | null;
  last_checked_at: string | null;
  last_changed_at: string | null;
  last_outcome: CheckOutcome | null;
  consecutive_failures: number;
  active: boolean;
  reason: string;
  snapshots: number;
  backfill: boolean;
};

export type SourceCheck = {
  id: string;
  started_at: string;
  finished_at: string | null;
  outcome: CheckOutcome;
  http_status: number | null;
  new_items: number;
  changes: number;
  error: string | null;
};

export type FilterTier = 0 | 1 | 2;

export type FilteredChange = {
  id: string;
  title: string;
  area: string;
  entity: EntityRef | null;
  detected_at: string;
  materiality: Materiality;
  filter_reason: string;
  detection_source: DetectionSource;
  source_url: string | null;
  tier: FilterTier;
};

export type LearnedRule = {
  id: string;
  kind: LearnedRuleKind;
  explanation: string;
  /** e.g. {area: "products", event_type: "content_change"} */
  scope: Record<string, string>;
  /** e.g. {threshold: "medium"} */
  effect: Record<string, string>;
  /** How many feedback items support it. */
  evidence_count: number;
  active: boolean;
  created_at: string;
  revoked_at: string | null;
};

// ---------------------------------------------------------------------------------------------
// 10. Agent runs (the "show your work" trace)
// ---------------------------------------------------------------------------------------------

export type Usage = {
  llm_calls: number;
  tool_calls: number;
  input_tokens: number;
  output_tokens: number;
  est_cost_usd: number;
};

export type RunSubjectType = "event" | "policy" | "source" | "report";

export type RunSummary = {
  id: string;
  agent: AgentName;
  status: RunStatus;
  title: string;
  subject: { type: RunSubjectType; id: string } | null;
  started_at: string | null;
  finished_at: string | null;
  usage: Usage;
};

export type RunBudget = { max_steps: number; max_tool_calls: number; max_seconds: number; max_cost_usd: number };

export type RunDetail = RunSummary & {
  task: Record<string, unknown>;
  budget: RunBudget;
  result: Record<string, unknown> | null;
  error: string | null;
  steps: RunStep[];
};

export type RunStep = {
  idx: number;
  kind: StepKind;
  /** Tool or model name. */
  name: string | null;
  /** One human line, e.g. "Searched news: 'Razorpay 0% fee'". */
  summary: string;
  /** JSON, may be truncated. */
  input: unknown;
  /** JSON, may be truncated. */
  output: unknown;
  tokens_in: number | null;
  tokens_out: number | null;
  latency_ms: number | null;
  created_at: string;
};

// ---------------------------------------------------------------------------------------------
// 11. Human approvals (consequential actions)
// ---------------------------------------------------------------------------------------------

export type Approval = {
  id: string;
  action_type: ApprovalActionType;
  title: string;
  /** e.g. {to: "...", subject: "...", body: "..."} */
  payload: Record<string, unknown>;
  /** Why the agent proposes it. */
  reason: string;
  /** "impact_analyst" | "user" */
  requested_by: string;
  report_id: string | null;
  status: ApprovalStatus;
  created_at: string;
  decided_at: string | null;
  decided_by: string | null;
  /** Note the decider left when approving or rejecting. */
  decision_note?: string | null;
  result: Record<string, unknown> | null;
};

export type ApprovalDecision = "approve" | "reject";

// ---------------------------------------------------------------------------------------------
// 12. Notifications (inbox)
// ---------------------------------------------------------------------------------------------

export type NotificationChannel = "inbox" | "slack" | "email" | "digest";
export type NotificationStatus = "pending" | "sent" | "failed" | "digest_queued";

export type NotificationItem = {
  id: string;
  report_id: string;
  title: string;
  severity: Severity;
  team: string | null;
  channel: NotificationChannel;
  status: NotificationStatus;
  created_at: string;
  read_at: string | null;
};

// ---------------------------------------------------------------------------------------------
// 13. Demo lab (sandbox pages; only when `sandbox_enabled`)
// ---------------------------------------------------------------------------------------------

export type SandboxPage = { slug: string; title: string; html: string; updated_at: string };

// ---------------------------------------------------------------------------------------------
// Request / response helpers (bodies and small responses named in the contract's tables)
// ---------------------------------------------------------------------------------------------

export type LoginInput = { email: string; password: string };
export type SignupInput = { email: string; password: string; name: string; org_name: string };

export type CreateWorkspaceInput = { name: string; profile?: CompanyProfile; teams?: TeamInput[] };
export type UpdateWorkspaceInput = { name?: string; profile?: CompanyProfile };
export type SeenResult = { previous_seen_at: string | null; seen_at: string };

export type CreatePlanInput = { request_text: string };
export type ApproveInput = { spec?: MonitoringPlan };

/**
 * Body of POST /reports/{rid}/share. The contract names the endpoint and its response
 * (`Approval`) but not the body; the UI collects a recipient and an optional note.
 * ASSUMPTION — documented in README ("Contract notes").
 */
export type ShareReportInput = { recipient: string; note?: string }; // backend accepts `recipient` as an alias of `to`

/** `historical` query param of GET /reports: live only, historical only, or both. */
export type HistoricalFilter = "false" | "true" | "all";

export type ReportsQuery = {
  severity?: Severity;
  area?: string;
  entity_id?: string;
  evidence_status?: EvidenceStatus;
  historical?: HistoricalFilter;
  limit?: number;
  /** ISO timestamp cursor on `detected_at`. */
  before?: string;
};

export type SourcePatch = { active?: boolean; check_every_hours?: number; priority?: Priority };
export type CheckEnqueued = { job_id: string };

export type DecideInput = { decision: ApprovalDecision; note?: string };

export type SandboxPageInput = { title?: string; html: string };
