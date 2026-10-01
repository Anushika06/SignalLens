import Link from "next/link";
import { AlertTriangle } from "lucide-react";

import { RelativeTime } from "@/components/common/relative-time";
import { Stat, StatGrid } from "@/components/common/stat";
import { Card, CardAction, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { formatNumber } from "@/lib/format";
import { routes } from "@/lib/routes";
import type { Overview } from "@/lib/types";

/** Are the sources SignalLens watches healthy, and when is the next check? */
export function SourcesHealth({ wid, sources }: { wid: string; sources: Overview["sources"] }) {
  const failing = sources.failing;
  return (
    <Card size="sm">
      <CardHeader>
        <CardTitle>Sources</CardTitle>
        <CardAction>
          <Link
            href={routes.monitoring(wid, "sources")}
            className="text-sm font-medium text-brand underline-offset-4 hover:underline"
          >
            Manage
          </Link>
        </CardAction>
      </CardHeader>
      <CardContent>
        {sources.total === 0 ? (
          <p className="text-sm text-pretty text-muted-foreground">
            No sources yet. They are created from the plan when you approve it, each with the reason it was chosen.
          </p>
        ) : (
          <StatGrid className="grid-cols-3">
            <Stat
              label="Active"
              value={
                <>
                  {formatNumber(sources.active)}
                  <span className="text-sm font-normal text-muted-foreground"> / {formatNumber(sources.total)}</span>
                </>
              }
            />
            <Stat
              label="Failing"
              value={
                failing > 0 ? (
                  <span className="inline-flex items-center gap-1.5 text-red-600 dark:text-red-400">
                    <AlertTriangle className="size-4" aria-hidden="true" />
                    {formatNumber(failing)}
                  </span>
                ) : (
                  "0"
                )
              }
              hint={failing > 0 ? "Needs a look" : "All healthy"}
            />
            <Stat label="Next check" value={<RelativeTime value={sources.next_check_at} className="text-base" />} />
          </StatGrid>
        )}
      </CardContent>
    </Card>
  );
}
