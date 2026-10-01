"use client";

import { useEffect } from "react";
import { FileText, Filter } from "lucide-react";

import { cn } from "@/lib/utils";
import { AreaChip, MetaBadge } from "@/components/common/badges";
import { EntityLink, ExternalLink } from "@/components/common/links";
import { RelativeTime } from "@/components/common/relative-time";
import { EmptyState } from "@/components/common/states";
import { prettyUrl } from "@/lib/format";
import { DETECTION_SOURCE, FILTER_TIER, MATERIALITY } from "@/lib/labels";
import type { FilteredChange, FilterTier } from "@/lib/types";

import { scrollToFirstVisible } from "./scroll";

const TIERS: FilterTier[] = [0, 1, 2];

type FilteredRowProps = {
  wid: string;
  change: FilteredChange;
  highlighted: boolean;
  areaLabel: (key: string) => string;
};

function FilteredRow({ wid, change, highlighted, areaLabel }: FilteredRowProps) {
  const detection = DETECTION_SOURCE[change.detection_source];
  const DetectionIcon = detection.icon ?? FileText;
  return (
    <li
      id={`filtered-${change.id}`}
      className={cn("scroll-mt-24 space-y-2 px-4 py-3.5", highlighted && "bg-brand/5 ring-1 ring-brand/30 ring-inset")}
      aria-current={highlighted ? "true" : undefined}
    >
      <div className="flex flex-wrap items-start gap-x-3 gap-y-1.5">
        <MetaBadge meta={FILTER_TIER[change.tier]} />
        <p className="min-w-0 flex-1 basis-60 text-sm font-medium text-pretty">{change.title}</p>
        <RelativeTime value={change.detected_at} className="text-xs text-muted-foreground" />
      </div>
      <p className="text-sm text-pretty">
        <span className="text-muted-foreground">Why it was ignored: </span>
        {change.filter_reason}
      </p>
      <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1.5 text-xs text-muted-foreground">
        {change.entity ? (
          <EntityLink wid={wid} entity={change.entity} className="font-normal text-foreground" />
        ) : null}
        <AreaChip label={areaLabel(change.area)} />
        <span className="inline-flex items-center gap-1">
          Materiality <MetaBadge meta={MATERIALITY[change.materiality]} tooltip={false} />
        </span>
        <span className="inline-flex items-center gap-1">
          <DetectionIcon className="size-3" aria-hidden="true" />
          {detection.label}
        </span>
        {change.source_url ? (
          <ExternalLink href={change.source_url} className="max-w-64">
            {prettyUrl(change.source_url)}
          </ExternalLink>
        ) : null}
      </div>
    </li>
  );
}

type FilteredChangesPanelProps = {
  wid: string;
  changes: FilteredChange[];
  /** From `?event=`: highlighted and scrolled into view. */
  highlightId: string | null;
  areaLabel: (key: string) => string;
};

/**
 * "What we ignored and why": changes that were detected but stopped at the materiality gate.
 * Showing them is the point — it proves noise was removed on the user's behalf.
 */
export function FilteredChangesPanel({ wid, changes, highlightId, areaLabel }: FilteredChangesPanelProps) {
  const hasHighlight = Boolean(highlightId && changes.some((change) => change.id === highlightId));

  useEffect(() => {
    if (highlightId && hasHighlight) scrollToFirstVisible([`filtered-${highlightId}`]);
  }, [highlightId, hasHighlight]);

  return (
    <div className="space-y-5">
      <div className="space-y-3">
        <div className="space-y-1">
          <h2 className="text-sm font-semibold tracking-tight">What we ignored and why</h2>
          <p className="max-w-3xl text-sm text-pretty text-muted-foreground">
            Changes SignalLens detected but did not escalate. Nothing here was investigated or sent to anyone. Every change
            meets the cheapest filter first:
          </p>
        </div>
        <ul className="grid gap-2 sm:grid-cols-3" aria-label="Filter tiers">
          {TIERS.map((tier) => (
            <li key={tier} className="space-y-1.5 rounded-lg border bg-card p-3">
              <MetaBadge meta={FILTER_TIER[tier]} tooltip={false} />
              <p className="text-xs text-pretty text-muted-foreground">{FILTER_TIER[tier].description}</p>
            </li>
          ))}
        </ul>
      </div>

      {changes.length === 0 ? (
        <EmptyState
          icon={Filter}
          title="Nothing filtered yet"
          description="Every change a check finds passes through the materiality gate. Changes that don't clear it are listed here with the reason, so you can see the noise SignalLens removed for you."
        />
      ) : (
        <ul className="divide-y rounded-xl border bg-card">
          {changes.map((change) => (
            <FilteredRow
              key={change.id}
              wid={wid}
              change={change}
              highlighted={change.id === highlightId}
              areaLabel={areaLabel}
            />
          ))}
        </ul>
      )}
    </div>
  );
}
