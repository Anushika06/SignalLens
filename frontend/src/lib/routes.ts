/**
 * Every in-app URL, in one place. Screens link through these helpers so that query-string
 * conventions (e.g. the intelligence feed filters) stay consistent.
 */
import { withQuery } from "./api";
import type { ActivityItem, EvidenceStatus, Severity } from "./types";

/** Live = new reports only (default), historical = web-archive backfill, all = both. */
export type FeedView = "live" | "historical" | "all";

export type IntelQuery = {
  view?: FeedView;
  severity?: Severity;
  area?: string;
  /** Entity id. */
  entity?: string;
  evidence?: EvidenceStatus;
};

export type MonitoringTab = "areas" | "sources" | "rules" | "filtered";

const w = (wid: string) => `/w/${encodeURIComponent(wid)}`;

export const routes = {
  home: "/",
  login: (next?: string) => withQuery("/login", { next }),
  newWorkspace: "/new",
  /** `from` lets the lab link back to the workspace it was opened from. */
  lab: (fromWid?: string) => withQuery("/lab", { from: fromWid }),

  dashboard: (wid: string) => w(wid),
  plan: (wid: string, pid: string) => `${w(wid)}/plan/${encodeURIComponent(pid)}`,

  intel: (wid: string, query: IntelQuery = {}) => withQuery(`${w(wid)}/intel`, query),
  report: (wid: string, rid: string) => `${w(wid)}/intel/${encodeURIComponent(rid)}`,

  world: (wid: string) => `${w(wid)}/world`,
  entity: (wid: string, eid: string) => `${w(wid)}/world/${encodeURIComponent(eid)}`,

  monitoring: (wid: string, tab?: MonitoringTab, extra: Record<string, string> = {}) =>
    withQuery(`${w(wid)}/monitoring`, { tab, ...extra }),
  /** Opens the Sources tab with this source expanded. */
  source: (wid: string, sid: string) => withQuery(`${w(wid)}/monitoring`, { tab: "sources", source: sid }),
  /** Opens the filtered-changes log with this event highlighted. */
  filteredEvent: (wid: string, eventId: string) => withQuery(`${w(wid)}/monitoring`, { tab: "filtered", event: eventId }),

  /** `q` pre-fills the question box (e.g. from a card: "Ask about this"). */
  ask: (wid: string, q?: string) => withQuery(`${w(wid)}/ask`, { q }),

  runs: (wid: string) => `${w(wid)}/runs`,
  run: (wid: string, runId: string) => `${w(wid)}/runs/${encodeURIComponent(runId)}`,

  approvals: (wid: string) => `${w(wid)}/approvals`,
  settings: (wid: string) => `${w(wid)}/settings`,
};

/** Where an activity-feed item should take the user, if anywhere. */
export function activityHref(wid: string, link: ActivityItem["link"]): string | null {
  if (!link) return null;
  switch (link.type) {
    case "report":
      return routes.report(wid, link.id);
    case "run":
      return routes.run(wid, link.id);
    case "source":
      return routes.source(wid, link.id);
    case "plan":
      return routes.plan(wid, link.id);
    case "event":
      // Events without a report are changes that were filtered out; the log explains why.
      return routes.filteredEvent(wid, link.id);
  }
}
