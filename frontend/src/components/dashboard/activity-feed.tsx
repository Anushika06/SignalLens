import Link from "next/link";
import { ArrowRight } from "lucide-react";

import { cn } from "@/lib/utils";
import { RelativeTime } from "@/components/common/relative-time";
import { Card, CardAction, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { ACTIVITY_KIND, ACTIVITY_STATUS, TONE_BADGE } from "@/lib/labels";
import { activityHref, routes } from "@/lib/routes";
import type { ActivityItem } from "@/lib/types";

function LivePill() {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-xs text-muted-foreground">
      <span className="relative flex size-2" aria-hidden="true">
        <span className="absolute inline-flex size-full animate-ping rounded-full bg-emerald-500/60" />
        <span className="relative inline-flex size-2 rounded-full bg-emerald-500" />
      </span>
      Live
    </span>
  );
}

function ActivityRow({ wid, item }: { wid: string; item: ActivityItem }) {
  const kind = ACTIVITY_KIND[item.kind];
  const status = ACTIVITY_STATUS[item.status];
  const href = activityHref(wid, item.link);
  const Icon = kind.icon;
  return (
    <li className="flex gap-3 py-2.5">
      <span
        className={cn(
          "mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-full border",
          TONE_BADGE[status.tone],
          item.status === "running" && "animate-pulse",
        )}
      >
        <Icon className="size-3.5" aria-hidden="true" />
      </span>
      <div className="min-w-0 flex-1">
        <p className="text-sm leading-snug text-pretty">
          {href ? (
            <Link href={href} className="underline-offset-4 hover:text-brand hover:underline">
              {item.message}
            </Link>
          ) : (
            item.message
          )}
        </p>
        <p className="mt-0.5 flex items-center gap-1.5 text-xs text-muted-foreground">
          <span>{kind.label}</span>
          {item.status !== "info" ? (
            <>
              <span aria-hidden="true">·</span>
              <span>{status.label}</span>
            </>
          ) : null}
          <span aria-hidden="true">·</span>
          <RelativeTime value={item.at} />
        </p>
      </div>
    </li>
  );
}

/** What the agents are doing right now; refreshed every 5 s with the overview. */
export function ActivityFeed({ wid, items }: { wid: string; items: ActivityItem[] }) {
  return (
    <Card className="gap-0 pb-0">
      <CardHeader className="border-b">
        <CardTitle>Agent activity</CardTitle>
        <CardDescription>Checks, changes and investigations as they happen</CardDescription>
        <CardAction>
          <LivePill />
        </CardAction>
      </CardHeader>
      <CardContent className="px-0">
        {items.length === 0 ? (
          <p className="px-4 py-8 text-center text-sm text-pretty text-muted-foreground">
            No activity yet. Checks, detected changes and investigations appear here as soon as monitoring starts.
          </p>
        ) : (
          <ol className="max-h-[440px] divide-y overflow-y-auto px-4">
            {items.map((item) => (
              <ActivityRow key={item.id} wid={wid} item={item} />
            ))}
          </ol>
        )}
      </CardContent>
      <CardFooter className="justify-end py-2.5">
        <Link
          href={routes.runs(wid)}
          className="inline-flex items-center gap-1 text-sm font-medium text-brand underline-offset-4 hover:underline"
        >
          All agent runs
          <ArrowRight className="size-3.5" aria-hidden="true" />
        </Link>
      </CardFooter>
    </Card>
  );
}
