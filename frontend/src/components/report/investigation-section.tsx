"use client";

import Link from "next/link";
import { ArrowRight, ChevronDown } from "lucide-react";

import { MetaBadge } from "@/components/common/badges";
import { Section, TextBlock } from "@/components/common/page-header";
import { Stat, StatGrid } from "@/components/common/stat";
import { ErrorState } from "@/components/common/states";
import { RunTrace } from "@/components/runs/run-trace";
import { UsageInline } from "@/components/runs/run-usage";
import { Button } from "@/components/ui/button";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Skeleton } from "@/components/ui/skeleton";
import { formatDuration, formatNumber } from "@/lib/format";
import { isRunActive, useRun } from "@/lib/hooks";
import { RUN_STATUS } from "@/lib/labels";
import { routes } from "@/lib/routes";
import type { ReportDetail } from "@/lib/types";

/** Fetches the investigator run only once the trace is expanded (the content mounts lazily). */
function InlineTrace({ wid, runId }: { wid: string; runId: string }) {
  const { data: run, error, isLoading, mutate } = useRun(wid, runId);
  if (error && !run) return <ErrorState error={error} onRetry={() => void mutate()} className="py-6" />;
  if (isLoading || !run) {
    return (
      <div className="space-y-3" aria-busy="true" aria-label="Loading the agent's steps">
        {Array.from({ length: 4 }, (_, index) => (
          <div key={index} className="flex gap-3">
            <Skeleton className="size-8 shrink-0 rounded-full" />
            <Skeleton className="h-12 flex-1" />
          </div>
        ))}
      </div>
    );
  }
  return (
    <div className="space-y-4">
      <UsageInline usage={run.usage} />
      {run.steps.length > 0 ? (
        <RunTrace steps={run.steps} live={isRunActive(run.status)} />
      ) : (
        <p className="text-sm text-muted-foreground">The run hasn&apos;t recorded any steps yet.</p>
      )}
    </div>
  );
}

/** What the investigator agent did before this card was published, with its full trace on demand. */
export function InvestigationSection({ wid, report }: { wid: string; report: ReportDetail }) {
  const investigation = report.investigation;
  return (
    <Section
      id="investigation"
      title="Investigation"
      description="Before publishing, the investigator agent searched for sources that confirm or contradict the change."
    >
      {investigation ? (
        <div className="overflow-hidden rounded-xl border bg-card">
          <div className="space-y-4 p-4">
            <StatGrid className="grid-cols-2 sm:grid-cols-4">
              <Stat
                label="Status"
                value={<MetaBadge meta={RUN_STATUS[investigation.status]} tooltip={false} />}
                valueClassName="text-sm font-normal"
              />
              <Stat label="Steps" value={formatNumber(investigation.steps)} />
              <Stat label="Tool calls" value={formatNumber(investigation.tool_calls)} />
              <Stat label="Duration" value={formatDuration(investigation.duration_ms)} />
            </StatGrid>
            {investigation.conclusion ? (
              <div className="space-y-1.5">
                <h3 className="text-xs font-semibold tracking-wide text-muted-foreground uppercase">Conclusion</h3>
                <TextBlock text={investigation.conclusion} />
              </div>
            ) : null}
          </div>

          <Collapsible className="border-t">
            <CollapsibleTrigger className="group flex w-full items-center justify-between gap-2 px-4 py-3 text-left text-sm font-medium transition-colors hover:bg-muted/50 focus-visible:bg-muted/50 focus-visible:outline-none">
              Show the agent&apos;s steps
              <ChevronDown
                className="size-4 text-muted-foreground transition-transform group-data-[state=open]:rotate-180"
                aria-hidden="true"
              />
            </CollapsibleTrigger>
            <CollapsibleContent className="border-t px-4 py-4">
              <InlineTrace wid={wid} runId={investigation.run_id} />
            </CollapsibleContent>
          </Collapsible>

          <div className="flex flex-wrap gap-2 border-t px-3 py-2.5">
            <Button asChild variant="ghost" size="sm">
              <Link href={routes.run(wid, investigation.run_id)}>
                Full run trace
                <ArrowRight aria-hidden="true" />
              </Link>
            </Button>
            {report.analysis_run_id ? (
              <Button asChild variant="ghost" size="sm">
                <Link href={routes.run(wid, report.analysis_run_id)}>
                  Impact analysis run
                  <ArrowRight aria-hidden="true" />
                </Link>
              </Button>
            ) : null}
          </div>
        </div>
      ) : (
        <div className="space-y-2 rounded-xl border border-dashed p-4 text-sm text-pretty text-muted-foreground">
          <p>
            {report.is_historical
              ? "Historical changes reconstructed from the web archive are recorded without a live investigation."
              : "No investigation ran for this change."}
          </p>
          {report.analysis_run_id ? (
            <Link
              href={routes.run(wid, report.analysis_run_id)}
              className="inline-flex items-center gap-1 font-medium text-foreground underline-offset-4 hover:underline"
            >
              Impact analysis run
              <ArrowRight className="size-3.5" aria-hidden="true" />
            </Link>
          ) : null}
        </div>
      )}
    </Section>
  );
}
