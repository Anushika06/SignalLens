/**
 * Product vocabulary: every enum in the API contract mapped to the words, colour tone and icon
 * the UI uses for it. Components never hard-code these, so a label or colour changes in one
 * place.
 *
 * Colour conventions (from the contract): severity critical=red, high=orange, medium=amber,
 * low=blue. Evidence confirmed=green, corroborated=teal, single source=amber,
 * conflicting=violet, unverified=grey. Colour is never the only signal — every badge has text.
 */
import {
  AlertTriangle,
  Archive,
  Bell,
  Bot,
  Brain,
  CheckCircle2,
  CircleDashed,
  CircleHelp,
  CircleSlash,
  CircleX,
  ClipboardList,
  Database,
  Eye,
  FileText,
  Filter,
  GitCompareArrows,
  Globe,
  Info,
  Layers,
  type LucideIcon,
  Mail,
  MessageSquareText,
  Newspaper,
  RefreshCw,
  Scale,
  Search,
  Share2,
  ShieldAlert,
  ShieldCheck,
  Signpost,
  Sparkles,
  SplitSquareHorizontal,
  UserCheck,
  Users,
  Webhook,
  Wrench,
  XCircle,
} from "lucide-react";

import type {
  ActivityKind,
  ActivityStatus,
  AgentName,
  ApprovalActionType,
  ApprovalStatus,
  Authority,
  CheckOutcome,
  DetectionSource,
  EntityKind,
  EntityRole,
  EventStatus,
  EventType,
  EvidenceStatus,
  FeedbackReason,
  FeedbackVerdict,
  FilterTier,
  Importance,
  LearnedRuleKind,
  Materiality,
  NotificationChannel,
  NotificationStatus,
  ObservedVia,
  PolicyStatus,
  Priority,
  RunStatus,
  Severity,
  SourceClass,
  SourceKind,
  Stance,
  StepKind,
  WorkspaceStatus,
} from "./types";

// ---------------------------------------------------------------------------------------------
// Tones — the small, fixed palette every badge draws from.
// ---------------------------------------------------------------------------------------------

export type Tone = "red" | "orange" | "amber" | "green" | "teal" | "blue" | "violet" | "brand" | "gray";

/** Soft badge: tinted background, strong text, hairline border. */
export const TONE_BADGE: Record<Tone, string> = {
  red: "border-red-200 bg-red-50 text-red-700 dark:border-red-500/30 dark:bg-red-500/10 dark:text-red-300",
  orange:
    "border-orange-200 bg-orange-50 text-orange-700 dark:border-orange-500/30 dark:bg-orange-500/10 dark:text-orange-300",
  amber:
    "border-amber-200 bg-amber-50 text-amber-800 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-300",
  green:
    "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-500/30 dark:bg-emerald-500/10 dark:text-emerald-300",
  teal: "border-teal-200 bg-teal-50 text-teal-700 dark:border-teal-500/30 dark:bg-teal-500/10 dark:text-teal-300",
  blue: "border-blue-200 bg-blue-50 text-blue-700 dark:border-blue-500/30 dark:bg-blue-500/10 dark:text-blue-300",
  violet:
    "border-violet-200 bg-violet-50 text-violet-700 dark:border-violet-500/30 dark:bg-violet-500/10 dark:text-violet-300",
  brand: "border-brand/25 bg-brand/10 text-brand",
  gray: "border-border bg-muted text-muted-foreground",
};

/** Solid dot (severity dots, status pips). */
export const TONE_DOT: Record<Tone, string> = {
  red: "bg-red-500",
  orange: "bg-orange-500",
  amber: "bg-amber-500",
  green: "bg-emerald-500",
  teal: "bg-teal-500",
  blue: "bg-blue-500",
  violet: "bg-violet-500",
  brand: "bg-brand",
  gray: "bg-zinc-400 dark:bg-zinc-500",
};

/** Coloured text/icon on the page background. */
export const TONE_TEXT: Record<Tone, string> = {
  red: "text-red-600 dark:text-red-400",
  orange: "text-orange-600 dark:text-orange-400",
  amber: "text-amber-600 dark:text-amber-400",
  green: "text-emerald-600 dark:text-emerald-400",
  teal: "text-teal-600 dark:text-teal-400",
  blue: "text-blue-600 dark:text-blue-400",
  violet: "text-violet-600 dark:text-violet-400",
  brand: "text-brand",
  gray: "text-muted-foreground",
};

export type Meta = { label: string; tone: Tone; icon?: LucideIcon; description?: string };

// ---------------------------------------------------------------------------------------------
// The two axes of an intelligence card: severity (how much it matters) and evidence (how sure).
// ---------------------------------------------------------------------------------------------

export const SEVERITY_ORDER: Severity[] = ["critical", "high", "medium", "low"];

export const SEVERITY: Record<Severity, Meta> = {
  critical: { label: "Critical", tone: "red", description: "Needs attention today." },
  high: { label: "High", tone: "orange", description: "Worth acting on this week." },
  medium: { label: "Medium", tone: "amber", description: "Worth knowing; no immediate action." },
  low: { label: "Low", tone: "blue", description: "For the record." },
};

export const SEVERITY_EXPLAINER =
  "Severity is how much this matters to your company. It is set separately from evidence status, which is how sure we are.";

export const EVIDENCE_ORDER: EvidenceStatus[] = ["confirmed", "corroborated", "single_source", "conflicting", "unverified"];

/** Each status is computed by deterministic rules in code, never asserted by a model. */
export const EVIDENCE: Record<EvidenceStatus, Meta> = {
  confirmed: {
    label: "Confirmed",
    tone: "green",
    icon: ShieldCheck,
    description:
      "A primary source supports it: the company's own official site, the issuing regulator or a statutory registry.",
  },
  corroborated: {
    label: "Corroborated",
    tone: "teal",
    icon: Layers,
    description: "No primary source yet, but at least two independent publishers support it and none contradict it.",
  },
  single_source: {
    label: "Single source",
    tone: "amber",
    icon: CircleDashed,
    description: "Exactly one independent publisher supports it. Treat it as a lead until it is corroborated.",
  },
  conflicting: {
    label: "Conflicting",
    tone: "violet",
    icon: SplitSquareHorizontal,
    description:
      "Sources disagree: primary sources contradict each other or the claim, or independent sources both support and contradict it.",
  },
  unverified: {
    label: "Unverified",
    tone: "gray",
    icon: CircleHelp,
    description: "No verified supporting evidence yet.",
  },
};

export const EVIDENCE_EXPLAINER =
  "Evidence status is how sure we are. Quotes are checked against pages the agent actually fetched, and the status follows fixed rules.";

// ---------------------------------------------------------------------------------------------
// Materiality, importance, priority
// ---------------------------------------------------------------------------------------------

export const MATERIALITY: Record<Materiality, Meta> = {
  none: { label: "None", tone: "gray" },
  low: { label: "Low", tone: "blue" },
  medium: { label: "Medium", tone: "amber" },
  high: { label: "High", tone: "orange" },
  critical: { label: "Critical", tone: "red" },
};

export const IMPORTANCE_ORDER: Importance[] = ["critical", "high", "medium", "low"];

export const IMPORTANCE: Record<Importance, Meta> = {
  critical: { label: "Critical", tone: "red", description: "Alert the owning teams immediately." },
  high: { label: "High", tone: "orange", description: "Alert the owning teams immediately." },
  medium: { label: "Medium", tone: "amber", description: "Included in the daily digest." },
  low: { label: "Low", tone: "blue", description: "Included in the daily digest." },
};

export const PRIORITY_ORDER: Priority[] = ["high", "medium", "low"];

export const PRIORITY: Record<Priority, Meta> = {
  high: { label: "High", tone: "orange" },
  medium: { label: "Medium", tone: "amber" },
  low: { label: "Low", tone: "gray" },
};

// ---------------------------------------------------------------------------------------------
// Entities
// ---------------------------------------------------------------------------------------------

export const ENTITY_KIND: Record<EntityKind, Meta> = {
  company: { label: "Company", tone: "gray" },
  product: { label: "Product", tone: "gray" },
  regulator: { label: "Regulator", tone: "gray" },
  person: { label: "Person", tone: "gray" },
  organization: { label: "Organization", tone: "gray" },
  topic: { label: "Topic", tone: "gray" },
};

export const ENTITY_ROLE: Record<EntityRole, Meta> = {
  subject: { label: "Subject", tone: "brand", description: "What you asked SignalLens to monitor." },
  competitor: { label: "Competitor", tone: "orange" },
  regulator: { label: "Regulator", tone: "violet" },
  partner: { label: "Partner", tone: "teal" },
  us: { label: "Your company", tone: "green" },
  related: { label: "Related", tone: "gray" },
};

// ---------------------------------------------------------------------------------------------
// Sources and evidence
// ---------------------------------------------------------------------------------------------

export const SOURCE_KIND: Record<SourceKind, Meta> = {
  page: { label: "Page", tone: "gray", icon: Globe, description: "A page SignalLens snapshots and diffs." },
  news: { label: "News", tone: "gray", icon: Newspaper, description: "A news query watched for new items." },
};

export const AUTHORITY: Record<Authority, Meta> = {
  official: { label: "Official", tone: "green", description: "The entity's own official domain." },
  regulator: { label: "Regulator", tone: "violet", description: "The issuing regulator or a statutory registry." },
  independent: { label: "Independent", tone: "blue", description: "A distinct, independent publisher." },
  community: { label: "Community", tone: "gray", description: "Forums, social posts and other community sources." },
};

export const SOURCE_CLASS: Record<SourceClass, Meta> = {
  primary: {
    label: "Primary",
    tone: "green",
    description: "The entity's official domains, the issuing regulator, or a statutory registry.",
  },
  independent: {
    label: "Independent",
    tone: "blue",
    description: "A distinct publisher. Syndicated copies of the same text count once.",
  },
  community: { label: "Community", tone: "gray", description: "Community content. Never counts toward corroboration." },
};

export const STANCE: Record<Stance, Meta> = {
  supports: { label: "Supports", tone: "green", icon: CheckCircle2 },
  contradicts: { label: "Contradicts", tone: "red", icon: XCircle },
  context: { label: "Context", tone: "gray", icon: Info },
};

export const OBSERVED_VIA: Record<ObservedVia, Meta> = {
  live: { label: "Live check", tone: "brand" },
  archive: { label: "Web archive", tone: "gray", icon: Archive },
  news: { label: "News", tone: "blue" },
  user: { label: "Added by you", tone: "gray" },
};

export const CHECK_OUTCOME: Record<CheckOutcome, Meta> = {
  baseline: { label: "Baseline", tone: "blue", description: "First observation — recorded as the baseline, never alerted." },
  unchanged: { label: "Unchanged", tone: "gray" },
  not_modified: { label: "Not modified", tone: "gray", description: "The server reported no change since the last check." },
  changed: { label: "Changed", tone: "brand" },
  new_items: { label: "New items", tone: "brand" },
  no_new_items: { label: "No new items", tone: "gray" },
  degenerate: {
    label: "Degenerate",
    tone: "amber",
    description: "The page came back empty or as an error/challenge page, so it was not compared.",
  },
  blocked: { label: "Blocked", tone: "red", description: "Access was refused (robots.txt, bot protection or HTTP error)." },
  error: { label: "Error", tone: "red" },
};

export const FILTER_TIER: Record<FilterTier, Meta> = {
  0: { label: "Tier 0 · Noise", tone: "gray", description: "Only volatile tokens changed (timestamps, © year, session ids)." },
  1: { label: "Tier 1 · Rules", tone: "blue", description: "Boilerplate or a learned suppression rule." },
  2: { label: "Tier 2 · Model", tone: "violet", description: "A fast model judged it below the area's threshold." },
};

// ---------------------------------------------------------------------------------------------
// Events
// ---------------------------------------------------------------------------------------------

export const EVENT_TYPE: Record<EventType, string> = {
  value_change: "Value change",
  item_added: "Item added",
  item_removed: "Item removed",
  content_change: "Content change",
  product_launch: "Product launch",
  pricing: "Pricing",
  partnership: "Partnership",
  funding: "Funding",
  leadership: "Leadership",
  regulatory: "Regulatory",
  legal: "Legal",
  acquisition: "Acquisition",
  financials: "Financials",
  expansion: "Expansion",
  other: "Other",
};

export const EVENT_STATUS: Record<EventStatus, Meta> = {
  candidate: { label: "Candidate", tone: "gray" },
  filtered: { label: "Filtered", tone: "gray" },
  investigating: { label: "Investigating", tone: "blue" },
  analyzing: { label: "Analysing", tone: "blue" },
  published: { label: "Published", tone: "green" },
  dismissed: { label: "Dismissed", tone: "gray" },
  historical: { label: "Historical", tone: "gray" },
  failed: { label: "Failed", tone: "red" },
};

export const DETECTION_SOURCE: Record<DetectionSource, Meta> = {
  page_diff: { label: "Page change", tone: "gray", icon: GitCompareArrows },
  attribute: { label: "Tracked value", tone: "gray", icon: Database },
  news: { label: "News", tone: "gray", icon: Newspaper },
  backfill: { label: "Web archive backfill", tone: "gray", icon: Archive },
  manual: { label: "Manual", tone: "gray", icon: UserCheck },
};

// ---------------------------------------------------------------------------------------------
// Workspaces, plans and runs
// ---------------------------------------------------------------------------------------------

export const WORKSPACE_STATUS: Record<WorkspaceStatus, Meta> = {
  setup: { label: "Setting up", tone: "gray" },
  planning: { label: "Planning", tone: "blue" },
  awaiting_approval: { label: "Awaiting approval", tone: "amber" },
  baselining: { label: "Building baseline", tone: "blue" },
  monitoring: { label: "Monitoring", tone: "green" },
  paused: { label: "Paused", tone: "gray" },
};

export const POLICY_STATUS: Record<PolicyStatus, Meta> = {
  planning: { label: "Planning", tone: "blue" },
  pending_approval: { label: "Awaiting approval", tone: "amber" },
  active: { label: "Active", tone: "green" },
  superseded: { label: "Superseded", tone: "gray" },
  rejected: { label: "Rejected", tone: "gray" },
  failed: { label: "Failed", tone: "red" },
};

export const RUN_STATUS: Record<RunStatus, Meta> = {
  queued: { label: "Queued", tone: "gray" },
  running: { label: "Running", tone: "blue" },
  succeeded: { label: "Succeeded", tone: "green" },
  failed: { label: "Failed", tone: "red" },
  budget_exhausted: {
    label: "Budget exhausted",
    tone: "amber",
    description: "The run hit one of its hard limits (steps, tool calls, time or cost) and stopped.",
  },
};

export const AGENT: Record<AgentName, Meta> = {
  planner: { label: "Planner", tone: "gray", icon: ClipboardList, description: "Researches the request and proposes a plan." },
  investigator: {
    label: "Investigator",
    tone: "gray",
    icon: Search,
    description: "Looks for confirming and contradicting evidence.",
  },
  impact_analyst: {
    label: "Impact analyst",
    tone: "gray",
    icon: Brain,
    description: "Explains why a change matters to your company.",
  },
  extractor: { label: "Extractor", tone: "gray", icon: FileText, description: "Extracts tracked values from pages." },
  triage: { label: "Triage", tone: "gray", icon: Filter, description: "Turns news items into structured events." },
  materiality: { label: "Materiality", tone: "gray", icon: Scale, description: "Decides whether a change is meaningful." },
};

export const STEP_KIND: Record<StepKind, Meta> = {
  decision: { label: "Decision", tone: "brand", icon: Signpost },
  tool_call: { label: "Tool call", tone: "blue", icon: Wrench },
  observation: { label: "Observation", tone: "gray", icon: Eye },
  guardrail: { label: "Guardrail", tone: "amber", icon: ShieldAlert },
  llm_call: { label: "Model call", tone: "violet", icon: Sparkles },
  note: { label: "Note", tone: "gray", icon: MessageSquareText },
  state_update: { label: "State update", tone: "green", icon: Database },
  error: { label: "Error", tone: "red", icon: AlertTriangle },
};

// ---------------------------------------------------------------------------------------------
// Feedback and learning
// ---------------------------------------------------------------------------------------------

export const FEEDBACK_VERDICT: Record<FeedbackVerdict, string> = {
  relevant: "Relevant",
  not_relevant: "Not relevant",
};

export const FEEDBACK_REASON: Record<FeedbackReason, string> = {
  useful: "Useful",
  always_urgent: "Always tell me immediately",
  too_minor: "Too minor",
  not_our_area: "Not our area",
  wrong_entity: "Wrong company",
  inaccurate: "Inaccurate",
  already_known: "Already knew",
  duplicate: "Duplicate",
  other: "Other",
};

/** Reason chips offered after each verdict (contract §7), in display order. */
export const FEEDBACK_REASONS_BY_VERDICT: Record<FeedbackVerdict, FeedbackReason[]> = {
  relevant: ["useful", "always_urgent", "other"],
  not_relevant: ["too_minor", "not_our_area", "wrong_entity", "inaccurate", "already_known", "duplicate", "other"],
};

/** What SignalLens may learn from each reason (spec C10) — shown before the user submits. */
export const FEEDBACK_REASON_HINT: Partial<Record<FeedbackReason, string>> = {
  always_urgent: "SignalLens may raise this area to critical so you hear about it immediately.",
  too_minor: "After repeated signals, SignalLens raises the alert threshold for this area and change type.",
  not_our_area: "SignalLens may lower this area's importance so it goes to the digest instead.",
  wrong_entity: "SignalLens may exclude this match from entity resolution.",
  inaccurate: "SignalLens may stop counting this publisher toward corroboration.",
};

export const LEARNED_RULE_KIND: Record<LearnedRuleKind, Meta> = {
  materiality_threshold: { label: "Alert threshold", tone: "blue" },
  area_importance: { label: "Area importance", tone: "violet" },
  publisher_trust: { label: "Publisher trust", tone: "amber" },
  entity_exclusion: { label: "Entity exclusion", tone: "gray" },
};

// ---------------------------------------------------------------------------------------------
// Approvals, notifications, activity
// ---------------------------------------------------------------------------------------------

export const APPROVAL_STATUS: Record<ApprovalStatus, Meta> = {
  pending: { label: "Awaiting decision", tone: "amber" },
  approved: { label: "Approved", tone: "blue" },
  rejected: { label: "Rejected", tone: "gray" },
  executed: { label: "Done", tone: "green" },
  failed: { label: "Failed", tone: "red" },
};

export const APPROVAL_ACTION: Record<ApprovalActionType, Meta> = {
  send_external_email: { label: "Send external email", tone: "gray", icon: Mail },
  share_report_externally: { label: "Share report externally", tone: "gray", icon: Share2 },
  post_external_webhook: { label: "Post to external webhook", tone: "gray", icon: Webhook },
};

export const NOTIFICATION_CHANNEL: Record<NotificationChannel, string> = {
  inbox: "Inbox",
  slack: "Slack",
  email: "Email",
  digest: "Daily digest",
};

export const NOTIFICATION_STATUS: Record<NotificationStatus, Meta> = {
  pending: { label: "Pending", tone: "gray" },
  sent: { label: "Sent", tone: "green" },
  failed: { label: "Failed", tone: "red" },
  digest_queued: { label: "In next digest", tone: "blue" },
};

export const ACTIVITY_KIND: Record<ActivityKind, { label: string; icon: LucideIcon }> = {
  plan: { label: "Plan", icon: ClipboardList },
  baseline: { label: "Baseline", icon: Database },
  backfill: { label: "Backfill", icon: Archive },
  check: { label: "Check", icon: RefreshCw },
  change: { label: "Change", icon: GitCompareArrows },
  filtered: { label: "Filtered", icon: Filter },
  investigation: { label: "Investigation", icon: Search },
  report: { label: "Report", icon: FileText },
  notification: { label: "Notification", icon: Bell },
  approval: { label: "Approval", icon: UserCheck },
  error: { label: "Error", icon: AlertTriangle },
};

export const ACTIVITY_STATUS: Record<ActivityStatus, Meta> = {
  info: { label: "Info", tone: "gray" },
  running: { label: "Running", tone: "blue" },
  success: { label: "Done", tone: "green" },
  warning: { label: "Warning", tone: "amber" },
  error: { label: "Error", tone: "red" },
};

// Re-exported for components that need a generic icon for "who did this".
export const ACTOR_ICON = { agent: Bot, user: Users, none: CircleSlash, failed: CircleX } as const;
