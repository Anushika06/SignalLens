"use client";

import { Fragment, useEffect, useMemo, useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";

import { cn } from "@/lib/utils";
import { MetaBadge } from "@/components/common/badges";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { plural } from "@/lib/format";
import { PRIORITY } from "@/lib/labels";
import type { Priority, SourceView } from "@/lib/types";

import { scrollToFirstVisible } from "./scroll";
import { ActiveSwitch, CheckNowButton } from "./source-actions";
import { SourceDetails } from "./source-details";
import {
  Failures,
  NextCheck,
  OutcomeCell,
  ScheduleCell,
  SourceKindIcon,
  sourceName,
  SourceTarget,
} from "./source-parts";

const PRIORITY_RANK: Record<Priority, number> = { high: 0, medium: 1, low: 2 };

/** Active first; within those, failing sources first (they need attention), then by priority. */
function sortSources(sources: SourceView[]) {
  return [...sources].sort(
    (a, b) =>
      Number(b.active) - Number(a.active) ||
      Number(b.consecutive_failures > 0) - Number(a.consecutive_failures > 0) ||
      PRIORITY_RANK[a.priority] - PRIORITY_RANK[b.priority] ||
      sourceName(a).localeCompare(sourceName(b)),
  );
}

type SourcesPanelProps = {
  wid: string;
  sources: SourceView[];
  /** From `?source=`: expanded and scrolled into view. Remount the panel when it changes. */
  focusSourceId: string | null;
  areaLabel: (key: string) => string;
};

/**
 * Every source SignalLens checks. A table on wide screens and cards below `xl`; both share the
 * same cells, actions and expandable details.
 */
export function SourcesPanel({ wid, sources, focusSourceId, areaLabel }: SourcesPanelProps) {
  const [expanded, setExpanded] = useState<ReadonlySet<string>>(
    () => new Set(focusSourceId ? [focusSourceId] : []),
  );
  const sorted = useMemo(() => sortSources(sources), [sources]);
  const activeCount = sources.filter((source) => source.active).length;
  const failingCount = sources.filter((source) => source.active && source.consecutive_failures > 0).length;

  useEffect(() => {
    if (focusSourceId) scrollToFirstVisible([`source-row-${focusSourceId}`, `source-card-${focusSourceId}`]);
  }, [focusSourceId]);

  function toggle(id: string) {
    setExpanded((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  return (
    <div className="space-y-4">
      <p className="metric text-sm text-muted-foreground">
        {plural(sources.length, "source")} · {activeCount} active
        {failingCount > 0 ? (
          <>
            {" · "}
            <span className="font-medium text-red-600 dark:text-red-400">{failingCount} failing</span>
          </>
        ) : null}
      </p>

      {/* Wide screens: table. */}
      <div className="hidden overflow-hidden rounded-xl border bg-card xl:block">
        <Table>
          <TableHeader className="bg-muted/40">
            <TableRow className="hover:bg-transparent">
              <TableHead className="w-10 pl-3">
                <span className="sr-only">Details</span>
              </TableHead>
              <TableHead>Source</TableHead>
              <TableHead>Priority</TableHead>
              <TableHead>Check every</TableHead>
              <TableHead>Last check</TableHead>
              <TableHead>Next check</TableHead>
              <TableHead>Failures</TableHead>
              <TableHead>Active</TableHead>
              <TableHead className="pr-4 text-right">
                <span className="sr-only">Actions</span>
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {sorted.map((source) => {
              const open = expanded.has(source.id);
              const detailsId = `source-details-${source.id}`;
              return (
                <Fragment key={source.id}>
                  <TableRow
                    id={`source-row-${source.id}`}
                    className={cn(
                      "scroll-mt-24",
                      !source.active && "text-muted-foreground",
                      source.id === focusSourceId && "bg-brand/5",
                    )}
                  >
                    <TableCell className="w-10 pt-3 pl-3 align-top">
                      <Button
                        variant="ghost"
                        size="icon-xs"
                        onClick={() => toggle(source.id)}
                        aria-expanded={open}
                        aria-controls={detailsId}
                        aria-label={`${open ? "Hide" : "Show"} details for ${sourceName(source)}`}
                      >
                        <ChevronRight className={cn("transition-transform", open && "rotate-90")} aria-hidden="true" />
                      </Button>
                    </TableCell>
                    <TableCell className="max-w-sm py-3 whitespace-normal">
                      <div className="flex gap-3">
                        <SourceKindIcon source={source} />
                        <SourceTarget wid={wid} source={source} />
                      </div>
                    </TableCell>
                    <TableCell className="pt-3.5 align-top">
                      <MetaBadge meta={PRIORITY[source.priority]} tooltip={false} />
                    </TableCell>
                    <TableCell className="pt-3.5 align-top">
                      <ScheduleCell source={source} />
                    </TableCell>
                    <TableCell className="pt-3.5 align-top">
                      <OutcomeCell source={source} />
                    </TableCell>
                    <TableCell className="pt-3.5 align-top">
                      <NextCheck source={source} />
                    </TableCell>
                    <TableCell className="pt-3.5 align-top">
                      <Failures count={source.consecutive_failures} />
                    </TableCell>
                    <TableCell className="pt-3.5 align-top">
                      <ActiveSwitch wid={wid} source={source} />
                    </TableCell>
                    <TableCell className="pt-3 pr-4 text-right align-top">
                      <CheckNowButton wid={wid} source={source} />
                    </TableCell>
                  </TableRow>
                  {open ? (
                    <TableRow id={detailsId} className="bg-muted/20 hover:bg-muted/20">
                      <TableCell colSpan={9} className="p-0 whitespace-normal">
                        <SourceDetails wid={wid} source={source} areaLabel={areaLabel} idPrefix="row" />
                      </TableCell>
                    </TableRow>
                  ) : null}
                </Fragment>
              );
            })}
          </TableBody>
        </Table>
      </div>

      {/* Narrow screens: cards. */}
      <ul className="space-y-3 xl:hidden">
        {sorted.map((source) => {
          const open = expanded.has(source.id);
          const detailsId = `source-card-details-${source.id}`;
          return (
            <li
              key={source.id}
              id={`source-card-${source.id}`}
              className={cn(
                "scroll-mt-24 overflow-hidden rounded-xl border bg-card",
                source.id === focusSourceId && "border-brand/40 ring-2 ring-brand/15",
              )}
            >
              <div className="space-y-4 p-4">
                <div className="flex gap-3">
                  <SourceKindIcon source={source} />
                  <SourceTarget wid={wid} source={source} />
                </div>
                <dl className="grid grid-cols-2 gap-x-4 gap-y-3 sm:grid-cols-3 lg:grid-cols-5">
                  <div className="space-y-1">
                    <dt className="text-xs text-muted-foreground">Priority</dt>
                    <dd>
                      <MetaBadge meta={PRIORITY[source.priority]} tooltip={false} />
                    </dd>
                  </div>
                  <div className="space-y-1">
                    <dt className="text-xs text-muted-foreground">Check every</dt>
                    <dd>
                      <ScheduleCell source={source} />
                    </dd>
                  </div>
                  <div className="space-y-1">
                    <dt className="text-xs text-muted-foreground">Last check</dt>
                    <dd>
                      <OutcomeCell source={source} />
                    </dd>
                  </div>
                  <div className="space-y-1">
                    <dt className="text-xs text-muted-foreground">Next check</dt>
                    <dd>
                      <NextCheck source={source} />
                    </dd>
                  </div>
                  <div className="space-y-1">
                    <dt className="text-xs text-muted-foreground">Failures</dt>
                    <dd>
                      <Failures count={source.consecutive_failures} />
                    </dd>
                  </div>
                </dl>
                <div className="flex flex-wrap items-center gap-2 border-t pt-3">
                  <ActiveSwitch wid={wid} source={source} withLabel id={`active-card-${source.id}`} />
                  <div className="ml-auto flex items-center gap-1.5">
                    <CheckNowButton wid={wid} source={source} />
                    <Button
                      variant="ghost"
                      size="xs"
                      onClick={() => toggle(source.id)}
                      aria-expanded={open}
                      aria-controls={detailsId}
                    >
                      {open ? "Hide details" : "Details"}
                      <ChevronDown className={cn("transition-transform", open && "rotate-180")} aria-hidden="true" />
                    </Button>
                  </div>
                </div>
              </div>
              {open ? (
                <div id={detailsId} className="border-t bg-muted/20">
                  <SourceDetails wid={wid} source={source} areaLabel={areaLabel} idPrefix="card" />
                </div>
              ) : null}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
