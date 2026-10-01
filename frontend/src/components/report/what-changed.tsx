import { ArrowRight } from "lucide-react";

import { Section, TextBlock } from "@/components/common/page-header";
import type { ReportDetail } from "@/lib/types";

/** Big "Previous → Current" display. Uses <del>/<ins> so the change is also conveyed semantically. */
function StateTransition({
  previous,
  current,
  label,
}: {
  previous: string | null;
  current: string | null;
  label: string | null;
}) {
  return (
    <div className="rounded-xl border bg-card p-4 sm:p-5">
      {label ? <p className="mb-3 text-xs font-medium text-muted-foreground">{label}</p> : null}
      <div className="grid items-center gap-3 sm:grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] sm:gap-6">
        <div className="min-w-0">
          <p className="text-[11px] font-medium tracking-wide text-muted-foreground uppercase">Previous</p>
          {previous ? (
            <del className="metric mt-1 block text-lg leading-snug text-pretty text-muted-foreground decoration-muted-foreground/50 sm:text-xl">
              {previous}
            </del>
          ) : (
            <p className="mt-1 text-lg text-muted-foreground italic sm:text-xl">None recorded</p>
          )}
        </div>
        <ArrowRight className="size-5 rotate-90 text-muted-foreground sm:rotate-0" aria-hidden="true" />
        <div className="min-w-0">
          <p className="text-[11px] font-medium tracking-wide text-brand uppercase">Current</p>
          {current ? (
            <ins className="metric mt-1 block text-lg leading-snug font-semibold text-pretty no-underline sm:text-xl">
              {current}
            </ins>
          ) : (
            <p className="mt-1 text-lg font-semibold sm:text-xl">Removed</p>
          )}
        </div>
      </div>
    </div>
  );
}

/** Facts only: what the sources say changed, with no interpretation. */
export function WhatChanged({ report }: { report: ReportDetail }) {
  const hasStates = Boolean(report.previous_state || report.current_state);
  return (
    <Section id="what-changed" title="What changed" description="Facts only — what the sources say, without interpretation.">
      <div className="space-y-4">
        {hasStates ? (
          <StateTransition
            previous={report.previous_state}
            current={report.current_state}
            label={report.fact?.label ?? null}
          />
        ) : null}
        <TextBlock text={report.what_changed} />
      </div>
    </Section>
  );
}
