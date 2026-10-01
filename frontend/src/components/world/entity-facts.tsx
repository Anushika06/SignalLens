"use client";

import { useState } from "react";
import { History, ListChecks } from "lucide-react";

import { AreaChip, EvidenceBadge } from "@/components/common/badges";
import { Section } from "@/components/common/page-header";
import { RelativeTime } from "@/components/common/relative-time";
import { EmptyState } from "@/components/common/states";
import { useAreaLabels } from "@/components/monitoring/use-area-labels";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { plural } from "@/lib/format";
import type { EntitySummary, FactSummary } from "@/lib/types";

import { FactDrawer } from "./fact-drawer";

function byRecentChange(a: FactSummary, b: FactSummary) {
  return (b.last_changed_at ?? "").localeCompare(a.last_changed_at ?? "") || a.label.localeCompare(b.label);
}

function CurrentValue({ fact }: { fact: FactSummary }) {
  return fact.current ? (
    <span className="metric font-semibold text-pretty">{fact.current.value_display}</span>
  ) : (
    <span className="text-muted-foreground">Not observed yet</span>
  );
}

function HistoryButton({ fact, onOpen }: { fact: FactSummary; onOpen: () => void }) {
  return (
    <Button
      variant="outline"
      size="xs"
      onClick={onOpen}
      aria-label={`History of ${fact.label}: ${plural(fact.versions, "version")}`}
    >
      <History aria-hidden="true" />
      <span className="metric">{plural(fact.versions, "version")}</span>
    </Button>
  );
}

/** Typed values tracked for this entity; each opens its full version history in a drawer. */
export function EntityFacts({ wid, entity, facts }: { wid: string; entity: EntitySummary; facts: FactSummary[] }) {
  const areaLabel = useAreaLabels(wid);
  const [selected, setSelected] = useState<FactSummary | null>(null);
  const [open, setOpen] = useState(false);
  const sorted = [...facts].sort(byRecentChange);

  function openHistory(fact: FactSummary) {
    setSelected(fact);
    setOpen(true);
  }

  return (
    <Section
      id="facts"
      title="Tracked facts"
      description="Typed values SignalLens extracts and versions on every check. Open a fact to see how it changed over time."
    >
      {sorted.length === 0 ? (
        <EmptyState
          icon={ListChecks}
          title="No tracked facts yet"
          description="Facts come from the tracked attributes in your monitoring plan (a fee, a product list, a CEO). They appear after the first successful check of their sources."
        />
      ) : (
        <>
          {/* Desktop: a real table. */}
          <div className="hidden overflow-hidden rounded-xl border bg-card md:block">
            <Table>
              <TableHeader className="bg-muted/40">
                <TableRow className="hover:bg-transparent">
                  <TableHead className="pl-4">Fact</TableHead>
                  <TableHead>Area</TableHead>
                  <TableHead>Current value</TableHead>
                  <TableHead>Evidence</TableHead>
                  <TableHead>Last changed</TableHead>
                  <TableHead className="pr-4 text-right">History</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {sorted.map((fact) => (
                  <TableRow key={fact.id}>
                    <TableCell className="py-3 pl-4 whitespace-normal">
                      <p className="font-medium">{fact.label}</p>
                      <p className="font-mono text-[11px] text-muted-foreground">{fact.key}</p>
                    </TableCell>
                    <TableCell>
                      <AreaChip label={areaLabel(fact.area)} />
                    </TableCell>
                    <TableCell className="max-w-xs min-w-40 whitespace-normal">
                      <CurrentValue fact={fact} />
                    </TableCell>
                    <TableCell>
                      {fact.current ? (
                        <EvidenceBadge status={fact.current.evidence_status} />
                      ) : (
                        <span className="text-muted-foreground">—</span>
                      )}
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      <RelativeTime value={fact.last_changed_at} />
                    </TableCell>
                    <TableCell className="pr-4 text-right">
                      <HistoryButton fact={fact} onOpen={() => openHistory(fact)} />
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>

          {/* Mobile: stacked rows with the same information. */}
          <ul className="divide-y rounded-xl border bg-card md:hidden">
            {sorted.map((fact) => (
              <li key={fact.id} className="space-y-2 p-4">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="text-sm font-medium">{fact.label}</p>
                    <p className="truncate font-mono text-[11px] text-muted-foreground">{fact.key}</p>
                  </div>
                  <AreaChip label={areaLabel(fact.area)} className="shrink-0" />
                </div>
                <p className="text-sm">
                  <CurrentValue fact={fact} />
                </p>
                <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                  {fact.current ? <EvidenceBadge status={fact.current.evidence_status} /> : null}
                  {fact.last_changed_at ? (
                    <span>
                      Changed <RelativeTime value={fact.last_changed_at} />
                    </span>
                  ) : (
                    <span>No changes yet</span>
                  )}
                  <span className="ml-auto">
                    <HistoryButton fact={fact} onOpen={() => openHistory(fact)} />
                  </span>
                </div>
              </li>
            ))}
          </ul>
        </>
      )}

      <FactDrawer
        wid={wid}
        fact={selected}
        entityName={entity.name}
        open={open}
        onOpenChange={setOpen}
        areaLabel={areaLabel}
      />
    </Section>
  );
}
