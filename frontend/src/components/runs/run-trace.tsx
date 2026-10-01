"use client";

import { ChevronDown } from "lucide-react";

import { cn } from "@/lib/utils";
import { JsonView } from "@/components/common/json-view";
import { RelativeTime } from "@/components/common/relative-time";
import { Button } from "@/components/ui/button";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Spinner } from "@/components/ui/spinner";
import { formatDuration, formatNumber } from "@/lib/format";
import { STEP_KIND, TONE_TEXT } from "@/lib/labels";
import type { RunStep } from "@/lib/types";

import { stepVisual } from "./step-visuals";

function hasPayload(value: unknown) {
  return value !== null && value !== undefined && !(typeof value === "object" && Object.keys(value).length === 0);
}

function StepItem({ step, isLast }: { step: RunStep; isLast: boolean }) {
  const visual = stepVisual(step);
  const Icon = visual.icon;
  const emphasis =
    step.kind === "guardrail"
      ? "border-amber-200 bg-amber-50/60 dark:border-amber-500/25 dark:bg-amber-500/5"
      : step.kind === "error"
        ? "border-red-200 bg-red-50/60 dark:border-red-500/25 dark:bg-red-500/5"
        : "border-transparent";
  const showPayload = hasPayload(step.input) || hasPayload(step.output);
  const tokens = (step.tokens_in ?? 0) + (step.tokens_out ?? 0);

  return (
    <li className="relative flex gap-3 pb-3">
      {!isLast ? <span aria-hidden="true" className="absolute top-9 bottom-0 left-4 w-px bg-border" /> : null}
      <span
        className={cn(
          "relative z-10 mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-full border bg-background",
          TONE_TEXT[visual.tone],
        )}
      >
        <Icon className="size-4" aria-hidden="true" />
      </span>
      <div className={cn("min-w-0 flex-1 rounded-lg border px-3 py-2", emphasis)}>
        <p className="text-sm leading-snug text-pretty">{step.summary}</p>
        <p className="metric mt-1 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs text-muted-foreground">
          <span>
            #{step.idx} · {STEP_KIND[step.kind].label}
          </span>
          {step.name ? <code className="rounded bg-muted px-1 font-mono text-[11px]">{step.name}</code> : null}
          {step.latency_ms !== null ? <span>{formatDuration(step.latency_ms)}</span> : null}
          {tokens > 0 ? <span>{formatNumber(tokens)} tokens</span> : null}
          <RelativeTime value={step.created_at} />
        </p>
        {showPayload ? (
          <Collapsible className="mt-1">
            <CollapsibleTrigger asChild>
              <Button variant="ghost" size="xs" className="-ml-2 text-muted-foreground data-open:[&_svg]:rotate-180">
                Input &amp; output
                <ChevronDown className="transition-transform" aria-hidden="true" />
              </Button>
            </CollapsibleTrigger>
            <CollapsibleContent className="mt-2 grid gap-3 lg:grid-cols-2">
              <div className="min-w-0 space-y-1">
                <p className="text-xs font-medium text-muted-foreground">Input</p>
                <JsonView value={step.input} label={`Step ${step.idx} input`} maxHeight={280} />
              </div>
              <div className="min-w-0 space-y-1">
                <p className="text-xs font-medium text-muted-foreground">Output</p>
                <JsonView value={step.output} label={`Step ${step.idx} output`} maxHeight={280} />
              </div>
            </CollapsibleContent>
          </Collapsible>
        ) : null}
      </div>
    </li>
  );
}

type RunTraceProps = {
  steps: RunStep[];
  /** The run is still going: show a "working" row after the last step. */
  live?: boolean;
  className?: string;
};

/** Vertical timeline of a run's steps, each expandable to its raw input and output. */
export function RunTrace({ steps, live = false, className }: RunTraceProps) {
  const ordered = [...steps].sort((a, b) => a.idx - b.idx);
  return (
    <ol className={cn("relative", className)} aria-live={live ? "polite" : undefined}>
      {ordered.map((step, index) => (
        <StepItem key={step.idx} step={step} isLast={!live && index === ordered.length - 1} />
      ))}
      {live ? (
        <li className="flex items-center gap-3 pb-1">
          <span className="flex size-8 shrink-0 items-center justify-center rounded-full border border-dashed bg-background text-muted-foreground">
            <Spinner className="size-3.5" />
          </span>
          <span className="text-sm text-muted-foreground">Working on the next step…</span>
        </li>
      ) : null}
    </ol>
  );
}
