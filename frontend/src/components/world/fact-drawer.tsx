"use client";

import { Skeleton } from "@/components/ui/skeleton";
import { EvidenceBadge } from "@/components/common/badges";
import { ErrorState } from "@/components/common/states";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { humanize, plural } from "@/lib/format";
import { useFact } from "@/lib/hooks";
import type { FactSummary } from "@/lib/types";

import { FactHistory } from "./fact-history";

type FactDrawerProps = {
  wid: string;
  /** Stays set while the drawer animates closed, so the content doesn't flash. */
  fact: FactSummary | null;
  entityName: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  areaLabel: (key: string) => string;
};

/** Right-hand drawer with every recorded version of one fact (GET /facts/{fid}). */
export function FactDrawer({ wid, fact, entityName, open, onOpenChange, areaLabel }: FactDrawerProps) {
  const { data, error, isLoading, mutate } = useFact(wid, fact?.id ?? null);
  const current = data?.fact.current ?? fact?.current ?? null;

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="gap-0 data-[side=right]:w-full data-[side=right]:sm:max-w-md">
        <SheetHeader className="border-b pr-12">
          <SheetTitle>{fact?.label ?? "Fact history"}</SheetTitle>
          <SheetDescription>
            {data?.entity.name ?? entityName}
            {fact ? ` · ${areaLabel(fact.area)}` : null}
          </SheetDescription>
        </SheetHeader>

        <div className="flex-1 space-y-6 overflow-y-auto p-4">
          {fact ? (
            <div className="space-y-2 rounded-lg border bg-muted/30 p-3">
              <p className="text-xs text-muted-foreground">Current value</p>
              <p className="metric text-lg font-semibold text-pretty">
                {current?.value_display ?? <span className="text-muted-foreground">Not observed yet</span>}
              </p>
              <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                {current ? <EvidenceBadge status={current.evidence_status} /> : null}
                <code className="rounded bg-muted px-1 font-mono text-[11px]">{fact.key}</code>
                <span className="whitespace-nowrap">
                  {humanize(fact.value_type)} · {plural(data?.versions.length ?? fact.versions, "version")}
                </span>
              </div>
            </div>
          ) : null}

          <p className="text-xs text-pretty text-muted-foreground">
            <span className="font-medium text-foreground">Effective</span> is when a value took effect, when the source
            says so. <span className="font-medium text-foreground">Observed</span> is when SignalLens saw it — on a live
            check, or replayed from the web archive during the baseline.
          </p>

          {isLoading ? (
            <div className="space-y-4" aria-busy="true" aria-label="Loading history">
              {Array.from({ length: 3 }, (_, index) => (
                <div key={index} className="flex gap-3">
                  <Skeleton className="mt-1 size-3 rounded-full" />
                  <div className="flex-1 space-y-2">
                    <Skeleton className="h-4 w-1/2" />
                    <Skeleton className="h-3 w-3/4" />
                  </div>
                </div>
              ))}
            </div>
          ) : error ? (
            <ErrorState error={error} onRetry={() => void mutate()} />
          ) : data ? (
            <FactHistory versions={data.versions} />
          ) : null}
        </div>
      </SheetContent>
    </Sheet>
  );
}
