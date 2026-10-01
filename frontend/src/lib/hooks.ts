"use client";

/**
 * SWR hooks — one per API resource. Keys are the GET paths from `paths`, so a mutation can
 * refresh exactly the resources it touched with `revalidate(...)`.
 *
 * Polling follows the contract (no websockets in v1): overview/activity every 5 s, a plan
 * every 2 s while `planning`, a run every 2 s while it is queued or running.
 */
import useSWR, { mutate as globalMutate, type SWRConfiguration } from "swr";
import useSWRInfinite from "swr/infinite";

import { ApiError, paths, request } from "./api";
import type {
  AgentName,
  Approval,
  ApprovalStatus,
  EntityDetail,
  EntitySummary,
  FactDetail,
  FilteredChange,
  LearnedRule,
  Me,
  NotificationItem,
  Overview,
  PlanDetail,
  PolicyView,
  ReportDetail,
  ReportSummary,
  ReportsQuery,
  RunDetail,
  RunSummary,
  SandboxPage,
  SourceCheck,
  SourceView,
  SsoConfig,
  SystemConfig,
  Team,
  WorkspaceDetail,
  WorkspaceMember,
  WorkspaceSummary,
  ActivityItem,
  AskDetail,
  AskItem,
} from "./types";

/** Polling intervals in milliseconds. */
export const POLL = {
  overview: 5_000,
  activity: 5_000,
  planning: 2_000,
  runningRun: 2_000,
  notifications: 15_000,
  approvals: 15_000,
  sources: 30_000,
  reports: 30_000,
} as const;

type Key = string | null;

function useResource<T>(key: Key, config?: SWRConfiguration<T, ApiError>) {
  return useSWR<T, ApiError>(key, config);
}

// Conditional polling intervals. Two SWR details shape these:
// - They must be stable (module-level) functions. SWR restarts its polling timer whenever
//   `refreshInterval` changes identity, so an inline arrow function in a component that
//   re-renders often (e.g. a ticking "elapsed" clock) would never get to poll.
// - SWR evaluates the function when the hook mounts, before any data has arrived, and then
//   again after every poll. "No data yet" must therefore mean "keep polling"; the first
//   response then decides whether polling continues.

export function isRunActive(status: RunSummary["status"] | undefined) {
  return status === "running" || status === "queued";
}

const pollWhilePlanning = (plan?: PlanDetail) => (!plan || plan.status === "planning" ? POLL.planning : 0);
const pollWhileRunActive = (run?: RunDetail) => (!run || isRunActive(run.status) ? POLL.runningRun : 0);
const pollAlways = () => POLL.runningRun;
/** Fast while something is running; otherwise a slow refresh so newly started runs appear. */
const pollRunList = (runs?: RunSummary[]) =>
  !runs || runs.some((run) => isRunActive(run.status)) ? POLL.activity : POLL.sources;
const retryEvery2s = (_error: ApiError, _key: string, _config: unknown, retry: () => void) => {
  setTimeout(retry, POLL.runningRun);
};

/**
 * Revalidate every cached resource whose GET path matches. Pass a path prefix
 * (e.g. `paths.workspace(wid) + "/reports"`) or a predicate.
 */
export function revalidate(match: string | ((path: string) => boolean)) {
  const test = typeof match === "string" ? (path: string) => path.startsWith(match) : match;
  // Calling mutate with only a filter revalidates without touching cached data.
  return globalMutate((key) => typeof key === "string" && test(key.replace(/^\$inf\$/, "")));
}

// --- Auth & system ---------------------------------------------------------------------------

export function useMe() {
  return useResource<Me>(paths.me, { revalidateOnFocus: false });
}

/** Like useMe, but a 401 is just "not signed in" (used on /login to forward signed-in users). */
export function useOptionalMe() {
  return useSWR<Me, ApiError>(
    `${paths.me}#optional`,
    () => request<Me>("GET", paths.me, { redirectOn401: false }),
    { revalidateOnFocus: false, shouldRetryOnError: false },
  );
}

export function useSystemConfig() {
  return useResource<SystemConfig>(paths.systemConfig, { revalidateOnFocus: false });
}

// --- Workspaces --------------------------------------------------------------------------------

export function useWorkspaces() {
  return useResource<WorkspaceSummary[]>(paths.workspaces);
}

export function useWorkspace(wid: string | null) {
  return useResource<WorkspaceDetail>(wid ? paths.workspace(wid) : null);
}

export function useTeams(wid: string) {
  return useResource<Team[]>(paths.teams(wid));
}

export function useMembers(wid: string) {
  return useResource<WorkspaceMember[]>(paths.members(wid));
}

/** Single sign-on availability; a failure just means "no SSO button". */
export function useSsoConfig() {
  return useSWR<SsoConfig, ApiError>(
    paths.ssoConfig,
    () => request<SsoConfig>("GET", paths.ssoConfig, { redirectOn401: false }),
    { revalidateOnFocus: false, shouldRetryOnError: false },
  );
}

// --- Plans -------------------------------------------------------------------------------------

export function usePlan(wid: string, pid: string) {
  return useResource<PlanDetail>(paths.plan(wid, pid), { refreshInterval: pollWhilePlanning });
}

// --- Dashboard ---------------------------------------------------------------------------------

export function useOverview(wid: string) {
  return useResource<Overview>(paths.overview(wid), { refreshInterval: POLL.overview });
}

export function useActivity(wid: string, limit = 50) {
  return useResource<ActivityItem[]>(paths.activity(wid, limit), { refreshInterval: POLL.activity });
}

// --- Reports -----------------------------------------------------------------------------------

export const REPORTS_PAGE_SIZE = 50;

/**
 * Paginated report feed. Pages are fetched with the `before` cursor (the `detected_at` of the
 * last report on the previous page); a short page means there is nothing older.
 */
export function useReportsFeed(wid: string, query: Omit<ReportsQuery, "before" | "limit">) {
  const swr = useSWRInfinite<ReportSummary[], ApiError>(
    (pageIndex, previous: ReportSummary[] | null) => {
      if (previous && previous.length < REPORTS_PAGE_SIZE) return null;
      const before = pageIndex === 0 ? undefined : previous?.at(-1)?.detected_at;
      return paths.reports(wid, { ...query, limit: REPORTS_PAGE_SIZE, before });
    },
    { refreshInterval: POLL.reports, revalidateFirstPage: true },
  );
  const pages = swr.data ?? [];
  return {
    ...swr,
    reports: pages.flat(),
    hasMore: (pages.at(-1)?.length ?? 0) === REPORTS_PAGE_SIZE,
    isLoadingMore: swr.isValidating && swr.size > pages.length,
    loadMore: () => swr.setSize(swr.size + 1),
  };
}

export function useReport(wid: string, rid: string) {
  return useResource<ReportDetail>(paths.report(wid, rid));
}

// --- World state ---------------------------------------------------------------------------------

export function useEntities(wid: string) {
  return useResource<EntitySummary[]>(paths.entities(wid));
}

export function useEntity(wid: string, eid: string) {
  return useResource<EntityDetail>(paths.entity(wid, eid));
}

export function useFact(wid: string, fid: string | null) {
  return useResource<FactDetail>(fid ? paths.fact(wid, fid) : null);
}

// --- Monitoring configuration -----------------------------------------------------------------

export function usePolicy(wid: string) {
  return useResource<PolicyView>(paths.policy(wid), {
    // 404 simply means "no active policy yet" — don't hammer the API about it.
    shouldRetryOnError: (error: ApiError) => error.status !== 404,
  });
}

export function useSources(wid: string) {
  return useResource<SourceView[]>(paths.sources(wid), { refreshInterval: POLL.sources });
}

export function useSourceChecks(wid: string, sid: string | null, limit = 20) {
  return useResource<SourceCheck[]>(sid ? paths.sourceChecks(wid, sid, limit) : null);
}

export function useFilteredChanges(wid: string, limit = 50) {
  return useResource<FilteredChange[]>(paths.filtered(wid, limit));
}

export function useLearnedRules(wid: string) {
  return useResource<LearnedRule[]>(paths.learnedRules(wid));
}

// --- Agent runs --------------------------------------------------------------------------------

export function useRuns(wid: string, query: { agent?: AgentName; limit?: number } = {}) {
  return useResource<RunSummary[]>(paths.runs(wid, query), { refreshInterval: pollRunList });
}

/**
 * A run, polled every 2 s while it is queued or running.
 *
 * `live`: the caller knows the run should be progressing (e.g. its plan is still `planning`),
 * so keep polling whatever the last response was — including errors such as a 404 before the
 * worker has created the run. (SWR's polling pauses while a key holds an error, so errors are
 * retried on the same 2 s cadence instead.)
 */
export function useRun(wid: string, runId: string | null, options: { live?: boolean } = {}) {
  const live = options.live ?? false;
  return useResource<RunDetail>(runId ? paths.run(wid, runId) : null, {
    refreshInterval: live ? pollAlways : pollWhileRunActive,
    ...(live ? { onErrorRetry: retryEvery2s } : {}),
  });
}

// --- Approvals & notifications -----------------------------------------------------------------

export function useApprovals(wid: string, status?: ApprovalStatus) {
  return useResource<Approval[]>(paths.approvals(wid, status), { refreshInterval: POLL.approvals });
}

export const NOTIFICATIONS_LIMIT = 50;

export function useUnreadNotifications(wid: string) {
  return useResource<NotificationItem[]>(paths.notifications(wid, { unread: true, limit: NOTIFICATIONS_LIMIT }), {
    refreshInterval: POLL.notifications,
  });
}

// --- Demo lab ------------------------------------------------------------------------------------

export function useSandboxPages() {
  return useResource<SandboxPage[]>(paths.sandboxPages);
}

export function useSandboxPage(slug: string | null) {
  return useResource<SandboxPage>(slug ? paths.sandboxPage(slug) : null, { revalidateOnFocus: false });
}

// --- Ask -----------------------------------------------------------------------------------------

const pollAskHistory = (items?: AskItem[]) =>
  !items || items.some((item) => isRunActive(item.status)) ? POLL.runningRun : 0;
const pollAsk = (item?: AskDetail) => (!item || isRunActive(item.status) ? POLL.runningRun : 0);

/** Recent questions with their answers; polled every 2 s while one is still being answered. */
export function useAskHistory(wid: string) {
  return useResource<AskItem[]>(paths.askHistory(wid), { refreshInterval: pollAskHistory });
}

/** One question with its live trace; polled every 2 s while queued or running. */
export function useAsk(wid: string, runId: string | null) {
  return useResource<AskDetail>(runId ? paths.ask(wid, runId) : null, { refreshInterval: pollAsk });
}
