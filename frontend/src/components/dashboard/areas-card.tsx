import Link from "next/link";
import { ArrowRight } from "lucide-react";

import { MetaBadge } from "@/components/common/badges";
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { IMPORTANCE } from "@/lib/labels";
import { routes } from "@/lib/routes";
import type { OverviewArea } from "@/lib/types";

/**
 * The areas being watched and how much each matters. When feedback has changed an area's
 * importance (a learned rule), both values are shown so the adjustment is never silent.
 */
export function AreasCard({ wid, areas }: { wid: string; areas: OverviewArea[] }) {
  return (
    <Card size="sm">
      <CardHeader>
        <CardTitle>Areas</CardTitle>
        <CardDescription>Critical and high alert right away; the rest go to the digest</CardDescription>
        <CardAction>
          <Link
            href={routes.monitoring(wid, "areas")}
            className="text-sm font-medium text-brand underline-offset-4 hover:underline"
          >
            Details
          </Link>
        </CardAction>
      </CardHeader>
      <CardContent>
        <ul className="divide-y">
          {areas.map((area) => {
            const adjusted = area.effective_importance !== area.importance;
            const effective = IMPORTANCE[area.effective_importance];
            return (
              <li key={area.key} className="flex items-center justify-between gap-3 py-2 first:pt-0 last:pb-0">
                <span className="min-w-0 truncate text-sm">{area.label}</span>
                <span className="flex shrink-0 items-center gap-1.5">
                  {adjusted ? (
                    <>
                      <MetaBadge
                        meta={IMPORTANCE[area.importance]}
                        tooltip={false}
                        className="line-through opacity-60"
                      />
                      <ArrowRight className="size-3 text-muted-foreground" aria-label="changed to" />
                    </>
                  ) : null}
                  <MetaBadge
                    meta={effective}
                    tooltip={adjusted ? "Adjusted by a learned rule from your feedback. You can undo it in Monitoring." : effective.description}
                  />
                </span>
              </li>
            );
          })}
        </ul>
      </CardContent>
    </Card>
  );
}
