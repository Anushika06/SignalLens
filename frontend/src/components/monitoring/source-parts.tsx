import { AlertTriangle, FileText } from "lucide-react";

import { Chip, MetaBadge, WithTooltip } from "@/components/common/badges";
import { EntityLink, ExternalLink } from "@/components/common/links";
import { RelativeTime } from "@/components/common/relative-time";
import { formatInterval, prettyUrl } from "@/lib/format";
import { AUTHORITY, CHECK_OUTCOME, SOURCE_KIND } from "@/lib/labels";
import type { SourceView } from "@/lib/types";

/** Short human name for a source, used in toasts and accessible labels. */
export function sourceName(source: SourceView): string {
  if (source.kind === "news") return source.query ? `“${source.query}”` : "news query";
  return prettyUrl(source.url) || "page";
}

export function isSandboxUrl(url: string | null): boolean {
  return Boolean(url?.startsWith("sandbox://"));
}

export function SourceKindIcon({ source }: { source: SourceView }) {
  const meta = SOURCE_KIND[source.kind];
  const Icon = meta.icon ?? FileText;
  return (
    <span className="flex size-7 shrink-0 items-center justify-center rounded-md border bg-background text-muted-foreground">
      <Icon className="size-3.5" aria-hidden="true" />
      <span className="sr-only">{meta.label}</span>
    </span>
  );
}

/** What is checked: a page URL (or demo page) or a news query, plus its entity and authority. */
export function SourceTarget({ wid, source }: { wid: string; source: SourceView }) {
  return (
    <div className="min-w-0 space-y-1">
      <div className="flex min-w-0 items-center gap-1.5 text-sm">
        {source.kind === "news" ? (
          <span className="min-w-0 truncate font-medium">{source.query ? `“${source.query}”` : "News query"}</span>
        ) : isSandboxUrl(source.url) ? (
          <>
            <span className="min-w-0 truncate font-mono text-[13px]">{source.url}</span>
            <WithTooltip content="A fictional page from the Demo lab, used to demonstrate change detection on demand.">
              <Chip className="shrink-0">Demo</Chip>
            </WithTooltip>
          </>
        ) : (
          <ExternalLink href={source.url} className="max-w-full font-medium">
            {prettyUrl(source.url)}
          </ExternalLink>
        )}
        {!source.active ? <Chip className="shrink-0">Paused</Chip> : null}
      </div>
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
        <span>{source.kind === "news" ? "News search" : "Page"}</span>
        {source.entity ? (
          <>
            <span aria-hidden="true">·</span>
            <EntityLink wid={wid} entity={source.entity} className="font-normal" />
          </>
        ) : null}
        <MetaBadge meta={AUTHORITY[source.authority]} />
      </div>
    </div>
  );
}

const ADAPTIVE_EXPLAINER =
  "Adaptive scheduling: SignalLens checks more often after a source changes and backs off while it stays quiet. The base interval is the one set in your plan.";

/** Base interval, plus the adaptive interval currently in use when it differs. */
export function ScheduleCell({ source }: { source: SourceView }) {
  const adaptive = source.current_interval_hours !== source.check_every_hours;
  return (
    <WithTooltip content={ADAPTIVE_EXPLAINER}>
      <div className="w-fit text-sm">
        <p className="metric">{formatInterval(source.check_every_hours)}</p>
        {adaptive ? (
          <p className="metric text-xs text-muted-foreground">now {formatInterval(source.current_interval_hours).toLowerCase()}</p>
        ) : null}
      </div>
    </WithTooltip>
  );
}

export function OutcomeCell({ source }: { source: SourceView }) {
  if (!source.last_outcome) return <span className="text-sm text-muted-foreground">Not checked yet</span>;
  return (
    <div className="space-y-1">
      <MetaBadge meta={CHECK_OUTCOME[source.last_outcome]} />
      <p className="text-xs text-muted-foreground">
        <RelativeTime value={source.last_checked_at} />
      </p>
    </div>
  );
}

export function NextCheck({ source }: { source: SourceView }) {
  if (!source.active) return <span className="text-sm text-muted-foreground">Paused</span>;
  if (!source.next_check_at) return <span className="text-sm text-muted-foreground">Not scheduled</span>;
  return <RelativeTime value={source.next_check_at} className="text-sm" />;
}

export function Failures({ count }: { count: number }) {
  if (count === 0) return <span className="text-sm text-muted-foreground">None</span>;
  return (
    <span className="metric inline-flex items-center gap-1 text-sm font-medium text-red-600 dark:text-red-400">
      <AlertTriangle className="size-3.5" aria-hidden="true" />
      {count} in a row
    </span>
  );
}
