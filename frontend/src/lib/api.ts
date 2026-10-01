/**
 * Typed client for the SignalLens API (docs/api-contract.md).
 *
 * - All requests go to relative `/api/...` URLs; next.config.ts proxies them to the backend,
 *   so the `sl_session` cookie is first-party and `credentials: "include"` just works.
 * - Error responses (`{detail: string}`, or FastAPI's 422 `{detail: [{loc, msg, type}]}`) are
 *   thrown as `ApiError` with the HTTP status and a readable `detail`.
 * - A 401 anywhere except the auth forms sends the browser to `/login?next=<current page>`.
 *
 * Reads go through SWR (see hooks.ts) keyed by the URL builders in `paths`; writes use the
 * typed functions in `api`, one per contract endpoint.
 */
import type {
  AddMemberInput,
  Approval,
  ApproveInput,
  ApproveResult,
  CheckEnqueued,
  CreatePlanInput,
  CreateWorkspaceInput,
  DecideInput,
  EmailTestResult,
  FeedbackInput,
  FeedbackResult,
  LearnedRule,
  LoginInput,
  Me,
  MonitoringPlan,
  PlanDetail,
  ReportsQuery,
  SandboxPage,
  SandboxPageInput,
  SeenResult,
  ShareReportInput,
  SignupInput,
  SourcePatch,
  SourceView,
  Team,
  TeamInput,
  UpdateWorkspaceInput,
  WorkspaceDetail,
  WorkspaceMember,
  WorkspaceRole,
  AgentName,
  ApprovalStatus,
  AskInput,
  AskStarted,
} from "./types";

export class ApiError extends Error {
  readonly status: number;
  readonly detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

/** Status 0 means the request never reached the API (network down, proxy target not running). */
export function isApiError(error: unknown): error is ApiError {
  return error instanceof ApiError;
}

type Method = "GET" | "POST" | "PUT" | "PATCH" | "DELETE";

type RequestOptions = {
  body?: unknown;
  /** Defaults to true. Auth forms turn it off so a wrong password shows an error instead. */
  redirectOn401?: boolean;
  signal?: AbortSignal;
};

let redirectingToLogin = false;

function redirectToLogin() {
  if (typeof window === "undefined" || redirectingToLogin) return;
  if (window.location.pathname.startsWith("/login")) return;
  redirectingToLogin = true;
  const next = window.location.pathname + window.location.search;
  // A full navigation (not router.push) on purpose: the session is gone, so drop all
  // in-memory state. This module has no access to the React router anyway.
  // eslint-disable-next-line @next/next/no-location-assign-relative-destination
  window.location.assign(`/login?next=${encodeURIComponent(next)}`);
}

type ValidationIssue = { loc?: (string | number)[]; msg?: string };

async function readErrorDetail(res: Response): Promise<string> {
  const text = await res.text().catch(() => "");
  try {
    const data = JSON.parse(text) as { detail?: string | ValidationIssue[] };
    if (typeof data.detail === "string") return data.detail;
    if (Array.isArray(data.detail)) {
      return data.detail
        .map((issue) => {
          const field = (issue.loc ?? []).filter((part) => part !== "body").join(".");
          return field ? `${field}: ${issue.msg ?? "invalid"}` : (issue.msg ?? "Invalid request");
        })
        .join("; ");
    }
  } catch {
    // Not JSON — typically the dev proxy reporting that the backend is unreachable.
  }
  if (res.status >= 500) {
    return `The SignalLens API is not responding (HTTP ${res.status}). Check that the backend is running.`;
  }
  return res.statusText || `Request failed (HTTP ${res.status})`;
}

export async function request<T>(method: Method, path: string, options: RequestOptions = {}): Promise<T> {
  const { body, redirectOn401 = true, signal } = options;
  let res: Response;
  try {
    res = await fetch(path, {
      method,
      credentials: "include",
      cache: "no-store",
      headers: body === undefined ? { Accept: "application/json" } : { Accept: "application/json", "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new ApiError(0, "Can't reach SignalLens. Check your connection and that the backend is running.");
  }

  if (res.status === 401 && redirectOn401) redirectToLogin();
  if (!res.ok) throw new ApiError(res.status, await readErrorDetail(res));
  if (res.status === 204) return undefined as T;

  const text = await res.text();
  return (text ? JSON.parse(text) : undefined) as T;
}

/** Default SWR fetcher: every SWR key is a GET path built by `paths`. */
export function fetcher<T>(path: string): Promise<T> {
  return request<T>("GET", path);
}

// ---------------------------------------------------------------------------------------------
// URL builders — used as SWR keys, so the same resource always has the same cache key.
// ---------------------------------------------------------------------------------------------

type QueryValue = string | number | boolean | null | undefined;

export function withQuery(path: string, query: Record<string, QueryValue>): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value === undefined || value === null || value === "") continue;
    params.set(key, String(value));
  }
  const qs = params.toString();
  return qs ? `${path}?${qs}` : path;
}

const seg = encodeURIComponent;
const ws = (wid: string) => `/api/workspaces/${seg(wid)}`;

export const paths = {
  me: "/api/auth/me",
  health: "/api/health",
  systemConfig: "/api/system/config",

  workspaces: "/api/workspaces",
  workspace: (wid: string) => ws(wid),
  teams: (wid: string) => `${ws(wid)}/teams`,
  members: (wid: string) => `${ws(wid)}/members`,
  ssoConfig: "/api/auth/sso/config",

  plan: (wid: string, pid: string) => `${ws(wid)}/plans/${seg(pid)}`,

  overview: (wid: string) => `${ws(wid)}/overview`,
  activity: (wid: string, limit = 50) => withQuery(`${ws(wid)}/activity`, { limit }),

  reports: (wid: string, query: ReportsQuery = {}) => withQuery(`${ws(wid)}/reports`, query),
  report: (wid: string, rid: string) => `${ws(wid)}/reports/${seg(rid)}`,

  entities: (wid: string) => `${ws(wid)}/entities`,
  entity: (wid: string, eid: string) => `${ws(wid)}/entities/${seg(eid)}`,
  fact: (wid: string, fid: string) => `${ws(wid)}/facts/${seg(fid)}`,

  policy: (wid: string) => `${ws(wid)}/policy`,
  sources: (wid: string) => `${ws(wid)}/sources`,
  sourceChecks: (wid: string, sid: string, limit = 20) => withQuery(`${ws(wid)}/sources/${seg(sid)}/checks`, { limit }),
  filtered: (wid: string, limit = 50) => withQuery(`${ws(wid)}/filtered`, { limit }),
  learnedRules: (wid: string) => `${ws(wid)}/learned-rules`,

  runs: (wid: string, query: { agent?: AgentName; limit?: number } = {}) => withQuery(`${ws(wid)}/runs`, query),
  run: (wid: string, runId: string) => `${ws(wid)}/runs/${seg(runId)}`,

  approvals: (wid: string, status?: ApprovalStatus) => withQuery(`${ws(wid)}/approvals`, { status }),
  notifications: (wid: string, query: { unread?: boolean; limit?: number } = {}) =>
    withQuery(`${ws(wid)}/notifications`, query),

  sandboxPages: "/api/sandbox/pages",
  sandboxPage: (slug: string) => `/api/sandbox/pages/${seg(slug)}`,

  askHistory: (wid: string, limit = 20) => withQuery(`${ws(wid)}/ask`, { limit }),
  ask: (wid: string, runId: string) => `${ws(wid)}/ask/${seg(runId)}`,
} as const;

// ---------------------------------------------------------------------------------------------
// Writes — one typed function per contract endpoint.
// ---------------------------------------------------------------------------------------------

/**
 * Where the "Continue with <provider>" button navigates (a full page load, not fetch): the
 * backend redirects to the identity provider and, after the callback, back to `next`.
 */
export function ssoStartUrl(next: string): string {
  return withQuery("/api/auth/sso/start", { next });
}

export const api = {
  auth: {
    login: (body: LoginInput) => request<Me>("POST", "/api/auth/login", { body, redirectOn401: false }),
    signup: (body: SignupInput) => request<Me>("POST", "/api/auth/signup", { body, redirectOn401: false }),
    logout: () => request<void>("POST", "/api/auth/logout", { redirectOn401: false }),
  },

  workspaces: {
    create: (body: CreateWorkspaceInput) => request<WorkspaceDetail>("POST", paths.workspaces, { body }),
    update: (wid: string, body: UpdateWorkspaceInput) =>
      request<WorkspaceDetail>("PATCH", paths.workspace(wid), { body }),
    /** Records "seen now" for the current user; returns the previous value for "since your last visit". */
    markSeen: (wid: string) => request<SeenResult>("POST", `${ws(wid)}/seen`),
  },

  teams: {
    create: (wid: string, body: TeamInput) => request<Team>("POST", paths.teams(wid), { body }),
    update: (wid: string, tid: string, body: Partial<TeamInput>) =>
      request<Team>("PATCH", `${paths.teams(wid)}/${seg(tid)}`, { body }),
    remove: (wid: string, tid: string) => request<void>("DELETE", `${paths.teams(wid)}/${seg(tid)}`),
    /** Sends a test email to the team's saved recipients through the configured provider. */
    testEmail: (wid: string, tid: string) =>
      request<EmailTestResult>("POST", `${paths.teams(wid)}/${seg(tid)}/test-email`),
  },

  plans: {
    create: (wid: string, body: CreatePlanInput) => request<PlanDetail>("POST", `${ws(wid)}/plans`, { body }),
    /** Only allowed while the plan is `pending_approval`. */
    saveSpec: (wid: string, pid: string, spec: MonitoringPlan) =>
      request<PlanDetail>("PUT", `${paths.plan(wid, pid)}/spec`, { body: { spec } }),
    approve: (wid: string, pid: string, body: ApproveInput = {}) =>
      request<ApproveResult>("POST", `${paths.plan(wid, pid)}/approve`, { body }),
    reject: (wid: string, pid: string) => request<PlanDetail>("POST", `${paths.plan(wid, pid)}/reject`),
  },

  reports: {
    markRead: (wid: string, rid: string) => request<void>("POST", `${paths.report(wid, rid)}/read`),
    feedback: (wid: string, rid: string, body: FeedbackInput) =>
      request<FeedbackResult>("POST", `${paths.report(wid, rid)}/feedback`, { body }),
    /** Never shares anything directly: creates a pending approval for a human to decide. */
    share: (wid: string, rid: string, body: ShareReportInput) =>
      request<Approval>("POST", `${paths.report(wid, rid)}/share`, { body }),
  },

  sources: {
    update: (wid: string, sid: string, body: SourcePatch) =>
      request<SourceView>("PATCH", `${paths.sources(wid)}/${seg(sid)}`, { body }),
    checkNow: (wid: string, sid: string) => request<CheckEnqueued>("POST", `${paths.sources(wid)}/${seg(sid)}/check`),
  },

  learnedRules: {
    /** Undo: the rule stops applying and comes back with `active: false`. */
    revoke: (wid: string, id: string) => request<LearnedRule>("DELETE", `${paths.learnedRules(wid)}/${seg(id)}`),
  },

  members: {
    /** Adds an org account, or invites a new email (they sign in with single sign-on). */
    add: (wid: string, body: AddMemberInput) => request<WorkspaceMember>("POST", paths.members(wid), { body }),
    setRole: (wid: string, uid: string, role: WorkspaceRole) =>
      request<WorkspaceMember>("PATCH", `${paths.members(wid)}/${seg(uid)}`, { body: { role } }),
    remove: (wid: string, uid: string) => request<void>("DELETE", `${paths.members(wid)}/${seg(uid)}`),
  },

  approvals: {
    decide: (wid: string, aid: string, body: DecideInput) =>
      request<Approval>("POST", `${ws(wid)}/approvals/${seg(aid)}/decide`, { body }),
  },

  notifications: {
    readAll: (wid: string) => request<void>("POST", `${ws(wid)}/notifications/read-all`),
  },

  sandbox: {
    save: (slug: string, body: SandboxPageInput) => request<SandboxPage>("PUT", paths.sandboxPage(slug), { body }),
  },

  ask: {
    /** Queues the question; poll `paths.ask(wid, run_id)` for live steps and the cited answer. */
    create: (wid: string, body: AskInput) => request<AskStarted>("POST", `${ws(wid)}/ask`, { body }),
  },
};
