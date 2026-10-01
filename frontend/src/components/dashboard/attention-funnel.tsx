import Link from "next/link";
import { ArrowRight, Filter } from "lucide-react";

import { cn } from "@/lib/utils";
import { WithTooltip } from "@/components/common/badges";
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { formatNumber, plural } from "@/lib/format";
import { routes } from "@/lib/routes";
import type { Funnel } from "@/lib/types";

function percent(part: number, whole: number) {
  if (!whole) return "0%";
  const value = (part / whole) * 100;
  return `${value < 10 ? value.toFixed(1) : Math.round(value)}%`;
}

type Stage = {
  key: string;
  label: string;
  value: number;
  /** Pipeline stages use the accent; filtered noise is neutral. */
  noise?: boolean;
  explanation: string;
};

/**
 * The attention funnel: how many checks turned into changes, how many of those were noise,
 * and how few became intelligence. Checks are a headline number (a different unit); every
 * bar below shares one linear scale measured in changes, so the stages compare honestly.
 */
export function AttentionFunnel({ wid, funnel }: { wid: string; funnel: Funnel }) {
  const { checks, changes, filtered, material, investigated, published, window_days: days } = funnel;

  const stages: Stage[] = [
    {
      key: "changes",
      label: "Changes",
      value: changes,
      explanation: `${plural(changes, "check")} found a difference or new items — ${percent(changes, checks)} of all checks.`,
    },
    {
      key: "filtered",
      label: "Filtered out",
      value: filtered,
      noise: true,
      explanation: `${plural(filtered, "change")} ignored automatically: volatile tokens, boilerplate, your learned rules, or below the area's threshold.`,
    },
    {
      key: "material",
      label: "Material",
      value: material,
      explanation: `${plural(material, "change")} cleared the materiality threshold for their area — ${percent(material, changes)} of changes.`,
    },
    {
      key: "investigated",
      label: "Investigated",
      value: investigated,
      explanation: `${plural(investigated, "change")} investigated for confirming and contradicting evidence.`,
    },
    {
      key: "published",
      label: "Published",
      value: published,
      explanation: `${plural(published, "change")} became intelligence cards routed to your teams.`,
    },
  ];
  const scale = Math.max(...stages.map((stage) => stage.value), 1);
  const empty = checks === 0 && changes === 0;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Attention funnel</CardTitle>
        <CardDescription>Noise SignalLens removed for you</CardDescription>
        <CardAction className="text-xs text-muted-foreground">Last {plural(days, "day")}</CardAction>
      </CardHeader>
      <CardContent className="space-y-4">
        {empty ? (
          <p className="text-sm text-pretty text-muted-foreground">
            Once monitoring runs, this shows how many checks found changes, how many were noise, and how few needed
            your attention.
          </p>
        ) : (
          <>
            <p className="flex items-baseline gap-2">
              <span className="metric text-3xl font-semibold tracking-tight">{formatNumber(checks)}</span>
              <span className="text-sm text-muted-foreground">checks of pages and news feeds</span>
            </p>
            <ol className="space-y-1" aria-label={`Attention funnel, last ${days} days`}>
              {stages.map((stage) => (
                <li key={stage.key}>
                  <WithTooltip content={stage.explanation} focusable side="left">
                    <div className="grid grid-cols-[6.5rem_minmax(0,1fr)_2.75rem] items-center gap-3 rounded-md px-1 py-1 outline-none hover:bg-muted/60 focus-visible:ring-2 focus-visible:ring-ring">
                      <span className={cn("text-sm", stage.noise ? "text-muted-foreground" : "text-foreground")}>
                        {stage.label}
                      </span>
                      <span className="h-2" aria-hidden="true">
                        <span
                          className={cn(
                            "block h-full min-w-[3px] rounded-r-[4px]",
                            stage.noise ? "bg-muted-foreground/35" : "bg-chart-1",
                          )}
                          style={{ width: `${(stage.value / scale) * 100}%` }}
                        />
                      </span>
                      <span className="metric text-right text-sm font-medium">{formatNumber(stage.value)}</span>
                    </div>
                  </WithTooltip>
                </li>
              ))}
            </ol>
            <div className="flex flex-col gap-2 rounded-lg bg-muted/50 px-3 py-2.5 text-sm sm:flex-row sm:items-center sm:justify-between">
              <p className="flex items-start gap-2 text-pretty">
                <Filter className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
                <span>
                  <span className="metric font-medium">{percent(filtered, changes)}</span> of changes never needed
                  your attention.
                </span>
              </p>
              <Link
                href={routes.monitoring(wid, "filtered")}
                className="inline-flex shrink-0 items-center gap-1 text-sm font-medium text-brand underline-offset-4 hover:underline"
              >
                What was ignored
                <ArrowRight className="size-3.5" aria-hidden="true" />
              </Link>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}
