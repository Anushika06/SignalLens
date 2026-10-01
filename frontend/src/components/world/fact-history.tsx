import { Archive } from "lucide-react";

import { cn } from "@/lib/utils";
import { EvidenceBadge, ToneBadge } from "@/components/common/badges";
import { ExternalLink } from "@/components/common/links";
import { formatDate } from "@/lib/format";
import { OBSERVED_VIA } from "@/lib/labels";
import type { StateVersion } from "@/lib/types";

function effectiveTime(version: StateVersion) {
  return new Date(version.valid_from ?? version.observed_at).getTime();
}

type FactHistoryProps = {
  versions: StateVersion[];
  className?: string;
};

/**
 * Versioned history of one tracked fact, newest first. Each version keeps two times apart:
 * when it took effect ("Effective", if known) and when SignalLens saw it ("Observed").
 */
export function FactHistory({ versions, className }: FactHistoryProps) {
  const ordered = [...versions].sort((a, b) => effectiveTime(b) - effectiveTime(a));
  if (ordered.length === 0) {
    return <p className="text-sm text-muted-foreground">No recorded values yet.</p>;
  }
  return (
    <ol className={cn("relative", className)}>
      {ordered.map((version, index) => {
        const isCurrent = index === 0;
        const isLast = index === ordered.length - 1;
        const via = OBSERVED_VIA[version.observed_via];
        return (
          <li key={version.id} className="relative flex gap-3 pb-5 last:pb-0">
            {!isLast ? <span aria-hidden="true" className="absolute top-4 bottom-0 left-[5px] w-px bg-border" /> : null}
            <span
              aria-hidden="true"
              className={cn(
                "relative z-10 mt-1.5 size-[11px] shrink-0 rounded-full border-2",
                isCurrent ? "border-brand bg-brand" : "border-muted-foreground/40 bg-background",
                version.observed_via === "archive" && !isCurrent && "border-dashed",
              )}
            />
            <div className="min-w-0 flex-1 space-y-1.5">
              <div className="flex flex-wrap items-center gap-2">
                <span className={cn("metric text-sm", isCurrent ? "font-semibold" : "font-medium text-foreground/80")}>
                  {version.value_display}
                </span>
                {isCurrent ? <ToneBadge tone="brand">Current</ToneBadge> : null}
                <ToneBadge tone={via.tone} icon={version.observed_via === "archive" ? Archive : undefined}>
                  {via.label}
                </ToneBadge>
              </div>
              <p className="text-xs text-muted-foreground">
                {version.valid_from ? <>Effective {formatDate(version.valid_from)} · </> : null}
                Observed {formatDate(version.observed_at)}
              </p>
              <div className="flex flex-wrap items-center gap-2 text-xs">
                <EvidenceBadge status={version.evidence_status} />
                {version.source_url ? (
                  <ExternalLink href={version.source_url} className="max-w-full text-muted-foreground" />
                ) : null}
              </div>
            </div>
          </li>
        );
      })}
    </ol>
  );
}
