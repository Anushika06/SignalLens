import Link from "next/link";
import { Archive, ArrowRight, Lightbulb } from "lucide-react";

import { RelativeTime } from "@/components/common/relative-time";
import { EmptyState } from "@/components/common/states";
import { Card, CardAction, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { ReportRow } from "@/components/intel/report-row";
import { plural } from "@/lib/format";
import { routes } from "@/lib/routes";
import type { ReportSummary } from "@/lib/types";

type RecentIntelProps = {
  wid: string;
  reports: ReportSummary[];
  /** When the user last opened this dashboard (frozen for the visit), or null on a first visit. */
  lastSeenAt: string | null;
  historicalCount: number;
};

function ReportList({ wid, reports }: { wid: string; reports: ReportSummary[] }) {
  return (
    <ul className="divide-y">
      {reports.map((report) => (
        <li key={report.id}>
          <ReportRow wid={wid} report={report} />
        </li>
      ))}
    </ul>
  );
}

/**
 * Latest intelligence cards, split at the user's previous visit so "what changed since I last
 * checked" is answered at a glance.
 */
export function RecentIntel({ wid, reports, lastSeenAt, historicalCount }: RecentIntelProps) {
  const seenAt = lastSeenAt ? new Date(lastSeenAt).getTime() : null;
  const fresh = seenAt === null ? [] : reports.filter((report) => new Date(report.detected_at).getTime() > seenAt);
  const earlier = seenAt === null ? reports : reports.filter((report) => new Date(report.detected_at).getTime() <= seenAt);

  return (
    <Card className="gap-0 py-0">
      <CardHeader className="border-b py-4">
        <CardTitle>Intelligence</CardTitle>
        <CardDescription>Verified changes that matter to you, newest first</CardDescription>
        <CardAction>
          <Link
            href={routes.intel(wid)}
            className="inline-flex items-center gap-1 text-sm font-medium text-brand underline-offset-4 hover:underline"
          >
            View all
            <ArrowRight className="size-3.5" aria-hidden="true" />
          </Link>
        </CardAction>
      </CardHeader>

      {reports.length === 0 ? (
        <EmptyState
          icon={Lightbulb}
          className="m-4 border-dashed"
          title="No intelligence yet"
          description="When a monitored page or news stream changes materially, SignalLens verifies it with quoted evidence and publishes a card here. Most checks find nothing — that is the point."
        />
      ) : seenAt === null ? (
        <>
          <p className="border-b bg-muted/40 px-4 py-2 text-xs text-muted-foreground">
            Your first visit — everything below is new to you.
          </p>
          <ReportList wid={wid} reports={earlier} />
        </>
      ) : (
        <>
          <section aria-labelledby="since-last-visit">
            <h3
              id="since-last-visit"
              className="flex items-center gap-2 border-b bg-brand/5 px-4 py-2 text-xs font-semibold text-brand"
            >
              <span className="size-1.5 rounded-full bg-brand" aria-hidden="true" />
              Since your last visit
              <span className="font-normal">
                · {fresh.length === 0 ? "nothing new" : `${plural(fresh.length, "new card")}`}
              </span>
            </h3>
            {fresh.length > 0 ? <ReportList wid={wid} reports={fresh} /> : null}
          </section>
          {earlier.length > 0 ? (
            <section aria-labelledby="before-last-visit">
              <div className="flex items-center gap-3 border-y bg-muted/40 px-4 py-2">
                <h3 id="before-last-visit" className="text-xs font-medium text-muted-foreground">
                  Earlier
                </h3>
                <span className="h-px flex-1 bg-border" aria-hidden="true" />
                <span className="text-xs text-muted-foreground">
                  Last visit <RelativeTime value={lastSeenAt} />
                </span>
              </div>
              <ReportList wid={wid} reports={earlier} />
            </section>
          ) : null}
        </>
      )}

      {historicalCount > 0 ? (
        <CardFooter className="py-3">
          <Link
            href={routes.intel(wid, { view: "historical" })}
            className="inline-flex items-center gap-2 text-sm text-muted-foreground underline-offset-4 hover:text-foreground hover:underline"
          >
            <Archive className="size-4" aria-hidden="true" />
            {plural(historicalCount, "historical report")} from web-archive backfill
            <ArrowRight className="size-3.5" aria-hidden="true" />
          </Link>
        </CardFooter>
      ) : null}
    </Card>
  );
}
