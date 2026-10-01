"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Lightbulb, Radar } from "lucide-react";

import { MetaBadge } from "@/components/common/badges";
import { PageHeader, Section } from "@/components/common/page-header";
import { PageSkeleton } from "@/components/common/skeletons";
import { ErrorState } from "@/components/common/states";
import { Button } from "@/components/ui/button";
import { api, isApiError } from "@/lib/api";
import { plural } from "@/lib/format";
import { useOverview, useWorkspace } from "@/lib/hooks";
import { WORKSPACE_STATUS } from "@/lib/labels";
import { routes } from "@/lib/routes";
import type { Overview } from "@/lib/types";

import { ActivityFeed } from "./activity-feed";
import { AreasCard } from "./areas-card";
import { AttentionFunnel } from "./attention-funnel";
import { RecentIntel } from "./recent-intel";
import { SourcesHealth } from "./sources-health";
import { SubjectCards } from "./subject-cards";
import { WorkspaceCallouts } from "./workspace-callouts";

/** How long the user must be on the dashboard before it counts as "seen". */
const SEEN_DELAY_MS = 3_000;

/**
 * "Since your last visit" needs the previous visit time as it was when the page opened. The
 * overview is polled every 5 s and will report the new visit once we mark it seen, so the
 * first value is frozen for the lifetime of this page.
 */
function useFrozenLastSeen(wid: string, overview: Overview | undefined) {
  const [frozen, setFrozen] = useState<{ wid: string; value: string | null } | null>(null);
  if (overview && (frozen === null || frozen.wid !== wid)) {
    setFrozen({ wid, value: overview.last_seen_at });
  }
  return frozen?.wid === wid ? frozen.value : (overview?.last_seen_at ?? null);
}

/** Record the visit a few seconds after the dashboard has actually been shown. */
function useMarkSeen(wid: string, ready: boolean) {
  useEffect(() => {
    if (!ready) return;
    const timer = setTimeout(() => {
      api.workspaces.markSeen(wid).catch(() => {
        // Not worth interrupting the user: the next visit will simply show more as new.
      });
    }, SEEN_DELAY_MS);
    return () => clearTimeout(timer);
  }, [wid, ready]);
}

export function DashboardScreen({ wid }: { wid: string }) {
  const workspace = useWorkspace(wid);
  const overview = useOverview(wid);
  const lastSeenAt = useFrozenLastSeen(wid, overview.data);
  useMarkSeen(wid, Boolean(overview.data));

  if (workspace.error && !workspace.data) {
    return <ErrorState error={workspace.error} onRetry={() => workspace.mutate()} />;
  }
  if (!workspace.data || (!overview.data && !overview.error)) return <PageSkeleton />;

  const ws = workspace.data;
  const data = overview.data;
  const subjects = data?.subjects.map((subject) => subject.name) ?? ws.subjects;
  // Before a plan is approved there may be nothing to summarise yet; that is not an error.
  const overviewMissing = isApiError(overview.error) && [404, 409].includes(overview.error.status);

  const description =
    subjects.length > 0
      ? `Watching ${subjects.join(", ")}${data ? ` across ${plural(data.areas.length, "area")} and ${plural(data.sources.total, "source")}` : ""}.`
      : "Tell SignalLens what to watch; it researches, proposes a plan you approve, then monitors continuously.";

  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow={<MetaBadge meta={WORKSPACE_STATUS[ws.status]} tooltip={false} />}
        title={ws.name}
        description={description}
        actions={
          <>
            <Button asChild variant="outline">
              <Link href={routes.monitoring(wid)}>
                <Radar aria-hidden="true" />
                Monitoring setup
              </Link>
            </Button>
            <Button asChild>
              <Link href={routes.intel(wid)}>
                <Lightbulb aria-hidden="true" />
                Intelligence feed
              </Link>
            </Button>
          </>
        }
      />

      <WorkspaceCallouts wid={wid} workspace={ws} pendingApprovals={data?.pending_approvals ?? 0} />

      {data ? (
        <>
          {data.subjects.length > 0 || data.areas.length > 0 ? (
            <Section id="subjects" title="What you're monitoring">
              <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,24rem)]">
                <SubjectCards wid={wid} subjects={data.subjects} areas={data.areas} />
                {data.areas.length > 0 ? <AreasCard wid={wid} areas={data.areas} /> : null}
              </div>
            </Section>
          ) : null}

          <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,24rem)]">
            <RecentIntel
              wid={wid}
              reports={data.recent_reports}
              lastSeenAt={lastSeenAt}
              historicalCount={data.historical_count}
            />
            <div className="grid gap-6">
              <AttentionFunnel wid={wid} funnel={data.funnel} />
              <ActivityFeed wid={wid} items={data.activity} />
              <SourcesHealth wid={wid} sources={data.sources} />
            </div>
          </div>
        </>
      ) : overview.error && !overviewMissing ? (
        <ErrorState error={overview.error} onRetry={() => overview.mutate()} />
      ) : null}
    </div>
  );
}
