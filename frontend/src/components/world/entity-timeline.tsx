"use client";

import { useState } from "react";
import Link from "next/link";
import { Archive } from "lucide-react";

import { cn } from "@/lib/utils";
import { AreaChip, Chip, EvidenceBadge, SeverityDot, ToneBadge, WithTooltip } from "@/components/common/badges";
import { Section } from "@/components/common/page-header";
import { useAreaLabels } from "@/components/monitoring/use-area-labels";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { formatDate } from "@/lib/format";
import { EVENT_TYPE } from "@/lib/labels";
import { routes } from "@/lib/routes";
import type { EntityTimelineItem } from "@/lib/types";

type TimelineFilter = "all" | "live" | "historical";

function eventTime(item: EntityTimelineItem) {
  return new Date(item.occurred_at ?? item.detected_at).getTime();
}

function TimelineEntry({
  wid,
  item,
  isLast,
  areaLabel,
}: {
  wid: string;
  item: EntityTimelineItem;
  isLast: boolean;
  areaLabel: (key: string) => string;
}) {
  const historical = item.is_historical;
  return (
    <li className="relative flex gap-4 pb-6 last:pb-0">
      {!isLast ? (
        <span
          aria-hidden="true"
          className={cn("absolute top-4 bottom-0 left-[5px] w-px", historical ? "border-l border-dashed" : "bg-border")}
        />
      ) : null}
      <span
        aria-hidden="true"
        className={cn(
          "relative z-10 mt-1 size-[11px] shrink-0 rounded-full border-2",
          historical ? "border-dashed border-muted-foreground/50 bg-background" : "border-brand bg-brand",
        )}
      />
      <div className={cn("min-w-0 flex-1 space-y-1.5", historical && "text-foreground/80")}>
        <p className="metric text-xs text-muted-foreground">{formatDate(item.occurred_at ?? item.detected_at)}</p>
        <div className="flex items-start gap-2">
          {item.severity ? <SeverityDot severity={item.severity} className="mt-1.5" /> : null}
          {item.report_id ? (
            <Link
              href={routes.report(wid, item.report_id)}
              className="text-sm font-medium text-pretty underline-offset-4 hover:text-brand hover:underline"
            >
              {item.title}
            </Link>
          ) : (
            <span className="text-sm font-medium text-pretty">{item.title}</span>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
          <span className="mr-0.5">{EVENT_TYPE[item.event_type]}</span>
          <AreaChip label={areaLabel(item.area)} />
          <EvidenceBadge status={item.evidence_status} />
          {!item.severity ? (
            <WithTooltip content="Recorded in the world state, but it did not produce an intelligence card.">
              <Chip>No card</Chip>
            </WithTooltip>
          ) : null}
          {historical ? (
            <ToneBadge tone="gray" icon={Archive}>
              Historical · web archive
            </ToneBadge>
          ) : null}
        </div>
        <p className="text-xs text-muted-foreground">
          {item.occurred_at ? <>Occurred {formatDate(item.occurred_at)} · </> : null}
          Detected {formatDate(item.detected_at)}
        </p>
      </div>
    </li>
  );
}

/**
 * Everything recorded for this entity, newest first. Historical items were replayed from the
 * web archive at baseline: they fill in the past but never alerted anyone.
 */
export function EntityTimeline({ wid, items }: { wid: string; items: EntityTimelineItem[] }) {
  const areaLabel = useAreaLabels(wid);
  const [filter, setFilter] = useState<TimelineFilter>("all");
  const sorted = [...items].sort((a, b) => eventTime(b) - eventTime(a));
  const liveCount = sorted.filter((item) => !item.is_historical).length;
  const historicalCount = sorted.length - liveCount;
  const visible = sorted.filter((item) =>
    filter === "all" ? true : filter === "historical" ? item.is_historical : !item.is_historical,
  );

  return (
    <Section
      id="timeline"
      title="Timeline"
      description="Changes recorded for this entity. Historical items come from the web archive and never trigger alerts."
      actions={
        sorted.length > 0 && historicalCount > 0 && liveCount > 0 ? (
          <ToggleGroup
            type="single"
            variant="outline"
            size="sm"
            spacing={0}
            value={filter}
            onValueChange={(value) => value && setFilter(value as TimelineFilter)}
            aria-label="Show"
          >
            <ToggleGroupItem value="all">All</ToggleGroupItem>
            <ToggleGroupItem value="live">
              Live <span className="metric text-muted-foreground">{liveCount}</span>
            </ToggleGroupItem>
            <ToggleGroupItem value="historical">
              Historical <span className="metric text-muted-foreground">{historicalCount}</span>
            </ToggleGroupItem>
          </ToggleGroup>
        ) : null
      }
    >
      {sorted.length === 0 ? (
        <p className="rounded-xl border border-dashed p-4 text-sm text-pretty text-muted-foreground">
          Nothing recorded yet. Material changes, news events and — if backfill is on — the last year of archived
          history will build up here.
        </p>
      ) : (
        <ol className="rounded-xl border bg-card p-4">
          {visible.map((item, index) => (
            <TimelineEntry
              key={item.event_id}
              wid={wid}
              item={item}
              isLast={index === visible.length - 1}
              areaLabel={areaLabel}
            />
          ))}
        </ol>
      )}
    </Section>
  );
}
