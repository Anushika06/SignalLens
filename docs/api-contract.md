# SignalLens API Contract (v1)

Source of truth for the frontend ↔ backend interface. The backend implements exactly these
shapes (Pydantic models in `backend/signallens/api/schemas.py`). If the two ever disagree,
this file wins and the code is fixed.

- Base path: **`/api`** (backend listens on `http://127.0.0.1:8000`; the Next.js app proxies
  `/api/*` to it via `rewrites`, so the browser only ever talks to its own origin).
- Auth: httpOnly cookie `sl_session` set by `/api/auth/login` and `/api/auth/signup`. Every
  other route returns **401** without it → frontend redirects to `/login`.
- Errors: `{ "detail": string }` with 400/401/403/404/409/422 (422 = validation; FastAPI
  default shape `{detail: [{loc, msg, type}]}`).
- Timestamps: ISO-8601 strings in UTC (`"2026-09-28T10:15:00Z"`). IDs: UUID strings.
- Polling (no websockets in v1): overview/activity every 5 s; plan while `planning` every
  2 s; run detail while `running` every 2 s.

---

## 1. Shared enums

```ts
type Severity = "critical" | "high" | "medium" | "low";
type EvidenceStatus = "confirmed" | "corroborated" | "single_source" | "conflicting" | "unverified";
type Materiality = "none" | "low" | "medium" | "high" | "critical";
type Importance = "critical" | "high" | "medium" | "low";
type EntityKind = "company" | "product" | "regulator" | "person" | "organization" | "topic";
type EntityRole = "subject" | "competitor" | "regulator" | "partner" | "us" | "related";
type SourceKind = "page" | "news";
type Authority = "official" | "regulator" | "independent" | "community";
type SourceClass = "primary" | "independent" | "community";
type Stance = "supports" | "contradicts" | "context";
type EventStatus = "candidate" | "filtered" | "investigating" | "analyzing" | "published"
                 | "dismissed" | "historical" | "failed";
type EventType = "value_change" | "item_added" | "item_removed" | "content_change"
               | "product_launch" | "pricing" | "partnership" | "funding" | "leadership"
               | "regulatory" | "legal" | "acquisition" | "financials" | "expansion" | "other";
type DetectionSource = "page_diff" | "attribute" | "news" | "backfill" | "manual";
type WorkspaceStatus = "setup" | "planning" | "awaiting_approval" | "baselining" | "monitoring" | "paused";
type PolicyStatus = "planning" | "pending_approval" | "active" | "superseded" | "rejected" | "failed";
type RunStatus = "queued" | "running" | "succeeded" | "failed" | "budget_exhausted";
type AgentName = "planner" | "investigator" | "impact_analyst" | "extractor" | "triage" | "materiality";
type StepKind = "decision" | "tool_call" | "observation" | "guardrail" | "llm_call" | "note"
              | "state_update" | "error";
type FeedbackVerdict = "relevant" | "not_relevant";
type FeedbackReason = "useful" | "always_urgent" | "too_minor" | "not_our_area" | "wrong_entity"
                    | "inaccurate" | "already_known" | "duplicate" | "other";
type LearnedRuleKind = "materiality_threshold" | "area_importance" | "publisher_trust" | "entity_exclusion";
type ApprovalStatus = "pending" | "approved" | "rejected" | "executed" | "failed";
type ApprovalActionType = "send_external_email" | "share_report_externally" | "post_external_webhook";
type CheckOutcome = "baseline" | "unchanged" | "not_modified" | "changed" | "new_items" | "no_new_items"
                  | "degenerate" | "blocked" | "error";
type ActivityKind = "plan" | "baseline" | "backfill" | "check" | "change" | "filtered" | "investigation"
                  | "report" | "notification" | "approval" | "error";
```

UI conventions (frontend): severity colours critical=red, high=orange, medium=amber,
low=slate/blue. Evidence badges: confirmed=green, corroborated=teal, single_source=amber,
conflicting=red/purple, unverified=grey. Labels: `single_source` → "Single source".

---

## 2. Auth

| Method | Path | Body | Response |
|---|---|---|---|
| POST | `/api/auth/signup` | `{email, password, name, org_name}` | `Me` + cookie |
| POST | `/api/auth/login` | `{email, password}` | `Me` + cookie |
| POST | `/api/auth/logout` | — | `204` |
| GET | `/api/auth/me` | — | `Me` or 401 |

```ts
type Me = { user: { id: string; email: string; name: string }; org: { id: string; name: string } };
```

A demo user is seeded by `signallens seed-demo` (see README): `demo@signallens.app` /
`signallens-demo`.

---

## 3. System

| Method | Path | Response |
|---|---|---|
| GET | `/api/health` | `{ ok: boolean; db: boolean; worker_seen_at: string \| null }` |
| GET | `/api/system/config` | `SystemConfig` |

```ts
type SystemConfig = {
  llm: { provider: string | null; fast_model: string | null; reasoning_model: string | null; configured: boolean };
  search: { provider: string | null; configured: boolean };
  sandbox_enabled: boolean;     // demo lab pages available
  demo_login: boolean;          // show the demo-account shortcut on sign-in (off in production by default)
  version: string;
};
```

Frontend shows a dismissible banner when `llm.configured` or `search.configured` is false
("Add API keys in backend/.env to enable live research").

---

## 4. Workspaces, profile, teams

| Method | Path | Body | Response |
|---|---|---|---|
| GET | `/api/workspaces` | — | `WorkspaceSummary[]` |
| POST | `/api/workspaces` | `{name, profile?: CompanyProfile, teams?: TeamInput[]}` | `WorkspaceDetail` |
| GET | `/api/workspaces/{wid}` | — | `WorkspaceDetail` |
| PATCH | `/api/workspaces/{wid}` | `{name?, profile?}` | `WorkspaceDetail` |
| POST | `/api/workspaces/{wid}/seen` | — | `{ previous_seen_at: string \| null; seen_at: string }` |
| GET | `/api/workspaces/{wid}/teams` | — | `Team[]` |
| POST | `/api/workspaces/{wid}/teams` | `TeamInput` | `Team` |
| PATCH | `/api/workspaces/{wid}/teams/{tid}` | `Partial<TeamInput>` | `Team` |
| DELETE | `/api/workspaces/{wid}/teams/{tid}` | — | `204` |

```ts
type CompanyProfile = {          // "us" — used by impact analysis and routing
  company_name: string;          // "" allowed (profile optional)
  website: string | null;
  description: string;           // what we do, for whom
  products: string[];
  markets: string[];             // e.g. ["India", "SMB merchants"]
  competitors: string[];         // names the user already knows
  relationship_to_subjects: string; // free text, e.g. "Razorpay is our main competitor"
};
type WorkspaceSummary = {
  id: string; name: string; status: WorkspaceStatus; created_at: string;
  subjects: string[];            // names of subject entities
  unread_reports: number;
};
type WorkspaceDetail = WorkspaceSummary & {
  profile: CompanyProfile;
  teams: Team[];
  active_policy_id: string | null;
  pending_policy_id: string | null;   // plan being prepared or awaiting approval
  last_seen_at: string | null;        // for the current user
};
type TeamInput = { name: string; areas: string[]; members: string[]; slack_webhook_url?: string | null };
type Team = { id: string; name: string; areas: string[]; members: string[]; slack_configured: boolean };
```

Default teams created with a new workspace when `teams` omitted: Strategy (all areas),
Product (products, pricing, technology), Compliance (regulation, legal), Sales & BD
(partnerships, pricing, customers), Leadership (funding, leadership, acquisitions).

---

## 5. Monitoring plans (onboarding + human approval)

| Method | Path | Body | Response |
|---|---|---|---|
| POST | `/api/workspaces/{wid}/plans` | `{request_text: string}` | `PlanDetail` (status `planning`) |
| GET | `/api/workspaces/{wid}/plans/{pid}` | — | `PlanDetail` |
| PUT | `/api/workspaces/{wid}/plans/{pid}/spec` | `{spec: MonitoringPlan}` | `PlanDetail` (only when `pending_approval`) |
| POST | `/api/workspaces/{wid}/plans/{pid}/approve` | `{spec?: MonitoringPlan}` | `ApproveResult` |
| POST | `/api/workspaces/{wid}/plans/{pid}/reject` | — | `PlanDetail` |

```ts
type PlanDetail = {
  id: string; version: number; status: PolicyStatus;
  request_text: string;
  run_id: string | null;             // planner run — show its steps live while planning
  spec: MonitoringPlan | null;       // null while planning
  error: string | null;
  created_at: string; approved_at: string | null;
};
type MonitoringPlan = {
  summary: string;
  domain: { industry: string; sector: string; geographies: string[]; rationale: string };
  entities: PlanEntity[];
  areas: PlanArea[];
  attributes: PlanAttribute[];
  sources: PlanSource[];
  open_questions: string[];
};
type PlanEntity = {
  ref: string;                       // stable key within the plan, e.g. "razorpay"
  name: string; kind: EntityKind; role: EntityRole;
  aliases: string[]; official_domains: string[];
  description: string; reason: string; enabled: boolean;
};
type PlanArea = {
  key: string;                       // "pricing"
  label: string;                     // "Pricing & fees"
  description: string; importance: Importance; reason: string;
  route_to: string[];                // team names
  enabled: boolean;
};
type PlanAttribute = {
  key: string;                       // "pricing.standard_domestic_fee"
  entity_ref: string; area: string; label: string;
  value_type: "percent" | "money" | "number" | "text" | "list" | "date" | "boolean";
  hint: string;                      // what exactly to extract
  source_refs: string[];             // which PlanSource.ref(s) contain it
  enabled: boolean;
};
type PlanSource = {
  ref: string; kind: SourceKind;
  url: string | null;                // for kind "page"
  query: string | null;              // for kind "news"
  entity_ref: string; areas: string[];
  authority: Authority; priority: "high" | "medium" | "low";
  check_every_hours: number;
  backfill: boolean;                 // replay web-archive history at baseline (pages only)
  reason: string; enabled: boolean;
  validation: SourceValidation | null;
};
type SourceValidation = {
  ok: boolean; http_status: number | null; robots_allowed: boolean | null;
  quality: "ok" | "degenerate" | "blocked" | null; title: string | null; note: string | null;
};
type ApproveResult = { policy_id: string; status: "active"; sources_created: number; jobs_enqueued: number };
```

---

## 6. Dashboard overview

`GET /api/workspaces/{wid}/overview` → `Overview`

```ts
type Overview = {
  workspace: WorkspaceSummary;
  last_seen_at: string | null;
  subjects: SubjectCard[];
  areas: { key: string; label: string; importance: Importance; effective_importance: Importance }[];
  funnel: Funnel;
  recent_reports: ReportSummary[];      // newest first, max 12, excludes historical
  historical_count: number;             // backfilled historical reports available
  activity: ActivityItem[];             // newest first, max 20
  pending_approvals: number;
  sources: { total: number; active: number; failing: number; next_check_at: string | null };
};
type SubjectCard = {
  entity_id: string; name: string; kind: EntityKind; role: EntityRole;
  areas: string[]; facts_count: number; reports_30d: number; last_change_at: string | null;
};
type Funnel = {                         // last 7 days
  window_days: number;
  checks: number; changes: number; filtered: number; material: number;
  investigated: number; published: number;
};
type ActivityItem = {
  id: string; at: string; kind: ActivityKind; message: string;
  status: "info" | "running" | "success" | "warning" | "error";
  link: { type: "report" | "run" | "source" | "event" | "plan"; id: string } | null;
};
```

`GET /api/workspaces/{wid}/activity?limit=50` → `ActivityItem[]`

---

## 7. Intelligence reports (cards)

| Method | Path | Response |
|---|---|---|
| GET | `/api/workspaces/{wid}/reports?severity=&area=&entity_id=&evidence_status=&historical=false&limit=50&before=` | `ReportSummary[]` |
| GET | `/api/workspaces/{wid}/reports/{rid}` | `ReportDetail` |
| POST | `/api/workspaces/{wid}/reports/{rid}/read` | `204` |
| POST | `/api/workspaces/{wid}/reports/{rid}/feedback` | `FeedbackResult` |
| POST | `/api/workspaces/{wid}/reports/{rid}/share` body `{to: string; note?: string}` (`recipient` accepted as an alias of `to`) | `Approval` (creates a pending external-share approval) |

`historical`: `false` (default) = live reports only; `true` = only backfilled historical;
`all` = both. `before` = ISO timestamp cursor on `detected_at`.

```ts
type ReportSummary = {
  id: string;
  title: string;                         // "Razorpay introduces 0% platform fee for first 90 days"
  change_label: string;                  // "Pricing change", "New partnership"
  area: string; area_label: string;
  entity: { id: string; name: string } | null;
  event_type: EventType;
  severity: Severity; evidence_status: EvidenceStatus;
  previous_state: string | null;         // "2% flat" (display string)
  current_state: string | null;          // "0% for first 90 days, then 2%"
  detected_at: string; occurred_at: string | null;
  is_historical: boolean;
  unread: boolean;
  feedback: { verdict: FeedbackVerdict; reason: FeedbackReason } | null;
};
type ReportDetail = ReportSummary & {
  what_changed: string;                  // facts only
  why_it_matters: string;                // agent assessment (label it as such in UI)
  considerations: string[];
  assumptions: string[];
  watch_next: string[];
  affected_teams: { id: string; name: string }[];
  evidence_summary: string;              // "Confirmed — official pricing page; 2 independent reports"
  evidence: Evidence[];
  fact: { id: string; key: string; label: string; history: StateVersion[] } | null;
  event: {
    id: string; status: EventStatus; detection_source: DetectionSource;
    materiality: Materiality; materiality_reason: string | null;
    source_url: string | null; diff_excerpt: string | null;
  };
  investigation: {
    run_id: string; status: RunStatus; steps: number; tool_calls: number;
    duration_ms: number | null; conclusion: string | null;
  } | null;
  analysis_run_id: string | null;
  approvals: Approval[];                 // proposed/decided external actions for this report
  related: ReportSummary[];              // same entity + area, max 5
};
type Evidence = {
  id: string; url: string; title: string | null; publisher: string;
  source_class: SourceClass; is_archive: boolean;
  stance: Stance; quote: string; quote_verified: boolean;
  published_at: string | null; retrieved_at: string;
  added_by: "pipeline" | "agent" | "user";
};
type StateVersion = {
  id: string; value_display: string;
  valid_from: string | null; observed_at: string;
  observed_via: "live" | "archive" | "news" | "user";
  evidence_status: EvidenceStatus;
  source_url: string | null; event_id: string | null;
};
type FeedbackInput = { verdict: FeedbackVerdict; reason: FeedbackReason; note?: string };
type FeedbackResult = {
  feedback: { id: string; verdict: FeedbackVerdict; reason: FeedbackReason; note: string | null; created_at: string };
  learned_rules: LearnedRule[];          // rules created or strengthened by this feedback (may be empty)
  message: string;                       // human sentence to show in a toast
};
```

Feedback reason chips (UI): for **relevant** — "Useful", "Always tell me immediately";
for **not relevant** — "Too minor", "Not our area", "Wrong company", "Inaccurate",
"Already knew", "Duplicate".

---

## 8. World state (entities, facts, timeline)

| Method | Path | Response |
|---|---|---|
| GET | `/api/workspaces/{wid}/entities` | `EntitySummary[]` |
| GET | `/api/workspaces/{wid}/entities/{eid}` | `EntityDetail` |
| GET | `/api/workspaces/{wid}/facts/{fid}` | `FactDetail` |

```ts
type EntitySummary = {
  id: string; name: string; kind: EntityKind; role: EntityRole;
  aliases: string[]; official_domains: string[]; description: string;
  facts_count: number; reports_count: number; last_change_at: string | null;
};
type FactSummary = {
  id: string; key: string; label: string; area: string; value_type: string;
  current: StateVersion | null; versions: number; last_changed_at: string | null;
};
type EntityDetail = {
  entity: EntitySummary;
  facts: FactSummary[];
  relationships: { id: string; predicate: string; direction: "out" | "in";
                   other: { id: string; name: string; kind: EntityKind };
                   first_seen_at: string; last_seen_at: string }[];
  timeline: { report_id: string | null; event_id: string; title: string; area: string;
              event_type: EventType; severity: Severity | null; evidence_status: EvidenceStatus;
              occurred_at: string | null; detected_at: string; is_historical: boolean }[];
};
type FactDetail = { fact: FactSummary; entity: { id: string; name: string }; versions: StateVersion[] };
```

---

## 9. Monitoring configuration, sources, learned rules, filtered changes

| Method | Path | Body | Response |
|---|---|---|---|
| GET | `/api/workspaces/{wid}/policy` | — | `PolicyView` |
| GET | `/api/workspaces/{wid}/sources` | — | `SourceView[]` |
| PATCH | `/api/workspaces/{wid}/sources/{sid}` | `{active?, check_every_hours?, priority?}` | `SourceView` |
| POST | `/api/workspaces/{wid}/sources/{sid}/check` | — | `{ job_id: string }` |
| GET | `/api/workspaces/{wid}/sources/{sid}/checks?limit=20` | — | `SourceCheck[]` |
| GET | `/api/workspaces/{wid}/filtered?limit=50` | — | `FilteredChange[]` |
| GET | `/api/workspaces/{wid}/learned-rules` | — | `LearnedRule[]` |
| DELETE | `/api/workspaces/{wid}/learned-rules/{id}` | — | `LearnedRule` (now `active: false`) |

```ts
type PolicyView = {
  id: string; version: number; status: PolicyStatus; approved_at: string | null;
  request_text: string; summary: string;
  areas: { key: string; label: string; importance: Importance; effective_importance: Importance;
           threshold: Materiality; route_to: string[] }[];
  spec: MonitoringPlan;
};
type SourceView = {
  id: string; kind: SourceKind; url: string | null; query: string | null;
  entity: { id: string; name: string } | null; areas: string[];
  authority: Authority; priority: "high" | "medium" | "low";
  check_every_hours: number;              // configured base interval
  current_interval_hours: number;         // adaptive interval in use
  next_check_at: string | null; last_checked_at: string | null; last_changed_at: string | null;
  last_outcome: CheckOutcome | null; consecutive_failures: number;
  active: boolean; reason: string; snapshots: number; backfill: boolean;
};
type SourceCheck = {
  id: string; started_at: string; finished_at: string | null; outcome: CheckOutcome;
  http_status: number | null; new_items: number; changes: number; error: string | null;
};
type FilteredChange = {
  id: string; title: string; area: string; entity: { id: string; name: string } | null;
  detected_at: string; materiality: Materiality; filter_reason: string;
  detection_source: DetectionSource; source_url: string | null; tier: 0 | 1 | 2;
};
type LearnedRule = {
  id: string; kind: LearnedRuleKind; explanation: string;
  scope: Record<string, string>;          // e.g. {area: "products", event_type: "content_change"}
  effect: Record<string, string>;         // e.g. {threshold: "medium"}
  evidence_count: number;                 // how many feedback items support it
  active: boolean; created_at: string; revoked_at: string | null;
};
```

---

## 10. Agent runs (the "show your work" trace)

| Method | Path | Response |
|---|---|---|
| GET | `/api/workspaces/{wid}/runs?agent=&limit=30` | `RunSummary[]` |
| GET | `/api/workspaces/{wid}/runs/{run_id}` | `RunDetail` |

```ts
type Usage = { llm_calls: number; tool_calls: number; input_tokens: number; output_tokens: number; est_cost_usd: number };
type RunSummary = {
  id: string; agent: AgentName; status: RunStatus; title: string;
  subject: { type: "event" | "policy" | "source" | "report"; id: string } | null;
  started_at: string | null; finished_at: string | null; usage: Usage;
};
type RunDetail = RunSummary & {
  task: Record<string, unknown>;
  budget: { max_steps: number; max_tool_calls: number; max_seconds: number; max_cost_usd: number };
  result: Record<string, unknown> | null;
  error: string | null;
  steps: RunStep[];
};
type RunStep = {
  idx: number; kind: StepKind; name: string | null;   // tool or model name
  summary: string;                                     // one human line: "Searched news: 'Razorpay 0% fee'"
  input: unknown; output: unknown;                     // JSON, may be truncated
  tokens_in: number | null; tokens_out: number | null; latency_ms: number | null;
  created_at: string;
};
```

---

## 11. Human approvals (consequential actions)

| Method | Path | Body | Response |
|---|---|---|---|
| GET | `/api/workspaces/{wid}/approvals?status=pending` | — | `Approval[]` |
| POST | `/api/workspaces/{wid}/approvals/{aid}/decide` | `{decision: "approve" \| "reject", note?: string}` | `Approval` |

```ts
type Approval = {
  id: string; action_type: ApprovalActionType; title: string;
  payload: Record<string, unknown>;       // e.g. {to: "...", subject: "...", body: "..."}
  reason: string;                          // why the agent proposes it
  requested_by: string;                    // "impact_analyst" | "user"
  report_id: string | null;
  status: ApprovalStatus; created_at: string;
  decided_at: string | null; decided_by: string | null; decision_note: string | null;
  result: Record<string, unknown> | null;
};
```

---

## 12. Notifications (inbox)

| Method | Path | Response |
|---|---|---|
| GET | `/api/workspaces/{wid}/notifications?unread=true&limit=50` | `NotificationItem[]` |
| POST | `/api/workspaces/{wid}/notifications/read-all` | `204` |

```ts
type NotificationItem = {
  id: string; report_id: string; title: string; severity: Severity;
  team: string | null; channel: "inbox" | "slack" | "email" | "digest";
  status: "pending" | "sent" | "failed" | "digest_queued"; created_at: string; read_at: string | null;
};
```

---

## 13. Demo lab (sandbox pages; only when `sandbox_enabled`)

Fictional pages served by the backend so a change can be demonstrated live on demand. A
sandbox page is monitored like any other page via the URL scheme `sandbox://<slug>`.

| Method | Path | Body | Response |
|---|---|---|---|
| GET | `/api/sandbox/pages` | — | `SandboxPage[]` |
| GET | `/api/sandbox/pages/{slug}` | — | `SandboxPage` |
| PUT | `/api/sandbox/pages/{slug}` | `{title?, html}` | `SandboxPage` |

```ts
type SandboxPage = { slug: string; title: string; html: string; updated_at: string };
```
