"use client";

import { useMemo } from "react";
import Link from "next/link";
import { Archive, FilterX, Lightbulb } from "lucide-react";

import { PageHeader } from "@/components/common/page-header";
import { ListSkeleton } from "@/components/common/skeletons";
import { EmptyState, ErrorState } from "@/components/common/states";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { plural } from "@/lib/format";
import { useReportsFeed } from "@/lib/hooks";
import { routes } from "@/lib/routes";

import { FeedFilterBar, FeedViewToggle } from "./feed-filters";
import { ReportRow } from "./report-row";
import { toReportsQuery, useFeedFilters, type FeedFilters } from "./use-feed-filters";

/**
 * The intelligence feed: every published card, newest first, filterable by severity, area,
 * entity and evidence status. Live shows new reports; Historical shows changes reconstructed
 * from the web archive when monitoring started.
 */
export function ReportFeedScreen({ wid }: { wid: string }) {
  const { filters, update, clear, hasFilters } = useFeedFilters();
  const query = useMemo(() => toReportsQuery(filters), [filters]);
  const feed = useReportsFeed(wid, query);
  const { reports, hasMore, isLoadingMore, loadMore } = feed;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Intelligence"
        description="Verified changes that matter to your company, each with its evidence and an assessment of why it matters."
        actions={<FeedViewToggle value={filters.view} onChange={(view) => update({ view })} />}
      />

      <div className="space-y-3">
        <FeedFilterBar wid={wid} filters={filters} hasFilters={hasFilters} onChange={update} onClear={clear} />
        {filters.view !== "live" ? (
          <p className="flex items-start gap-2 rounded-lg border bg-muted/40 px-3 py-2 text-xs text-pretty text-muted-foreground">
            <Archive className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
            Historical reports were reconstructed from web-archive captures of official pages when monitoring
            started. They add context and never trigger alerts.
          </p>
        ) : null}
      </div>

      {feed.error && reports.length === 0 ? (
        <ErrorState error={feed.error} onRetry={() => void feed.mutate()} />
      ) : feed.isLoading ? (
        <ListSkeleton rows={6} />
      ) : reports.length === 0 ? (
        <FeedEmptyState wid={wid} filters={filters} hasFilters={hasFilters} onClear={clear} />
      ) : (
        <section aria-label="Reports" className="space-y-3">
          <p className="metric text-xs text-muted-foreground" aria-live="polite">
            {hasMore ? `Showing the latest ${plural(reports.length, "report")}` : plural(reports.length, "report")}
          </p>
          <ul className="divide-y overflow-hidden rounded-xl border bg-card">
            {reports.map((report) => (
              <li key={report.id}>
                <ReportRow wid={wid} report={report} />
              </li>
            ))}
          </ul>
          {hasMore ? (
            <div className="flex justify-center pt-1">
              <Button variant="outline" onClick={() => void loadMore()} disabled={isLoadingMore}>
                {isLoadingMore ? <Spinner /> : null}
                {isLoadingMore ? "Loading…" : "Load older reports"}
              </Button>
            </div>
          ) : null}
        </section>
      )}
    </div>
  );
}

type FeedEmptyStateProps = {
  wid: string;
  filters: FeedFilters;
  hasFilters: boolean;
  onClear: () => void;
};

/** Explains why the feed is empty — which differs for filters, historical view and a fresh workspace. */
function FeedEmptyState({ wid, filters, hasFilters, onClear }: FeedEmptyStateProps) {
  if (hasFilters) {
    return (
      <EmptyState
        icon={FilterX}
        title="No reports match these filters"
        description="Try a wider severity or evidence range, or clear the filters to see everything."
        action={
          <Button variant="outline" size="sm" onClick={onClear}>
            Clear filters
          </Button>
        }
      />
    );
  }
  if (filters.view === "historical") {
    return (
      <EmptyState
        icon={Archive}
        title="No historical reports"
        description="When a plan is approved, SignalLens can replay about a year of web-archive captures of official pages to show what changed before monitoring began. Those reports appear here, labelled historical."
        action={
          <Button asChild variant="outline" size="sm">
            <Link href={routes.monitoring(wid, "sources")}>See monitored sources</Link>
          </Button>
        }
      />
    );
  }
  return (
    <EmptyState
      icon={Lightbulb}
      title="No intelligence yet"
      description="SignalLens checks your sources on a schedule. Most changes are noise and are filtered out; the material ones are investigated, verified with quoted evidence and published here as intelligence cards."
      action={
        <Button asChild variant="outline" size="sm">
          <Link href={routes.dashboard(wid)}>See what the agent is doing</Link>
        </Button>
      }
    />
  );
}
