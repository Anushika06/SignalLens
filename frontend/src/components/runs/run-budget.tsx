import { cn } from "@/lib/utils";
import { durationBetween, formatDuration, formatNumber, formatUsd } from "@/lib/format";
import type { RunDetail } from "@/lib/types";

type Meter = {
  label: string;
  used: number;
  max: number;
  format: (value: number) => string;
};

/** Ratio at which a meter turns amber: the run is close to a hard limit. */
const WARN_AT = 0.8;

function BudgetMeter({ label, used, max, format }: Meter) {
  const ratio = max > 0 ? used / max : 0;
  const percent = Math.min(100, Math.round(ratio * 100));
  const bar = ratio >= 1 ? "bg-red-500" : ratio >= WARN_AT ? "bg-amber-500" : "bg-primary";
  return (
    <div className="space-y-1.5">
      <div className="flex items-baseline justify-between gap-2 text-xs">
        <span className="text-muted-foreground">{label}</span>
        <span className="metric font-medium">
          {format(used)} <span className="font-normal text-muted-foreground">of {format(max)}</span>
        </span>
      </div>
      <div
        role="meter"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={max}
        aria-valuenow={Math.min(used, max)}
        aria-valuetext={`${format(used)} of ${format(max)}`}
        className="h-1.5 overflow-hidden rounded-full bg-muted"
      >
        <div className={cn("h-full rounded-full transition-[width] duration-500", bar)} style={{ width: `${percent}%` }} />
      </div>
    </div>
  );
}

/** How much of each hard limit the run has used: steps, tool calls, wall-clock time and cost. */
export function runMeters(run: RunDetail): Meter[] {
  const elapsedSeconds = (durationBetween(run.started_at, run.finished_at) ?? 0) / 1000;
  return [
    { label: "Steps", used: run.steps.length, max: run.budget.max_steps, format: formatNumber },
    { label: "Tool calls", used: run.usage.tool_calls, max: run.budget.max_tool_calls, format: formatNumber },
    {
      label: "Time",
      used: elapsedSeconds,
      max: run.budget.max_seconds,
      format: (seconds) => formatDuration(seconds * 1000),
    },
    { label: "Cost", used: run.usage.est_cost_usd, max: run.budget.max_cost_usd, format: formatUsd },
  ];
}

/** The limits a run reached (used ≥ max) — tells the reader why a run stopped early. */
export function exhaustedLimits(run: RunDetail): string[] {
  return runMeters(run)
    .filter((meter) => meter.max > 0 && meter.used >= meter.max)
    .map((meter) => meter.label.toLowerCase());
}

export function RunBudget({ run }: { run: RunDetail }) {
  return (
    <div className="space-y-4">
      {runMeters(run).map((meter) => (
        <BudgetMeter key={meter.label} {...meter} />
      ))}
    </div>
  );
}
