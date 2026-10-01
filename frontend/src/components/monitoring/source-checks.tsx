"use client";

import { MetaBadge, WithTooltip } from "@/components/common/badges";
import { RelativeTime } from "@/components/common/relative-time";
import { ErrorState } from "@/components/common/states";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { durationBetween, formatDuration, formatNumber } from "@/lib/format";
import { useSourceChecks } from "@/lib/hooks";
import { CHECK_OUTCOME } from "@/lib/labels";
import type { SourceCheck } from "@/lib/types";

function Duration({ check }: { check: SourceCheck }) {
  if (!check.finished_at) return <span className="text-muted-foreground">Running…</span>;
  return <span className="metric">{formatDuration(durationBetween(check.started_at, check.finished_at))}</span>;
}

/** The last checks of one source (GET /sources/{sid}/checks). */
export function SourceChecks({ wid, sid }: { wid: string; sid: string }) {
  const { data, error, isLoading, mutate } = useSourceChecks(wid, sid);

  if (isLoading) {
    return (
      <div className="space-y-2" aria-busy="true" aria-label="Loading checks">
        {Array.from({ length: 4 }, (_, index) => (
          <Skeleton key={index} className="h-8 w-full" />
        ))}
      </div>
    );
  }
  if (error) return <ErrorState error={error} onRetry={() => void mutate()} className="py-6" />;
  if (!data || data.length === 0) {
    return (
      <p className="rounded-lg border border-dashed p-3 text-sm text-muted-foreground">
        No checks yet. The first successful check records the baseline — it never raises an alert.
      </p>
    );
  }

  return (
    <div className="overflow-hidden rounded-lg border bg-background">
      <Table>
        <TableHeader className="bg-muted/40">
          <TableRow className="hover:bg-transparent">
            <TableHead className="pl-3">Started</TableHead>
            <TableHead>Outcome</TableHead>
            <TableHead className="text-right">HTTP</TableHead>
            <TableHead className="text-right">New items</TableHead>
            <TableHead className="text-right">Changes</TableHead>
            <TableHead className="text-right">Duration</TableHead>
            <TableHead className="pr-3">Error</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {data.map((check) => (
            <TableRow key={check.id}>
              <TableCell className="pl-3 text-muted-foreground">
                <RelativeTime value={check.started_at} />
              </TableCell>
              <TableCell>
                <MetaBadge meta={CHECK_OUTCOME[check.outcome]} />
              </TableCell>
              <TableCell className="metric text-right text-muted-foreground">{check.http_status ?? "—"}</TableCell>
              <TableCell className="metric text-right">{formatNumber(check.new_items)}</TableCell>
              <TableCell className="metric text-right">{formatNumber(check.changes)}</TableCell>
              <TableCell className="text-right">
                <Duration check={check} />
              </TableCell>
              <TableCell className="max-w-56 pr-3">
                {check.error ? (
                  <WithTooltip content={check.error}>
                    <span className="block truncate text-red-600 dark:text-red-400">{check.error}</span>
                  </WithTooltip>
                ) : (
                  <span className="text-muted-foreground">—</span>
                )}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
