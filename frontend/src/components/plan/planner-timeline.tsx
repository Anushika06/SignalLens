import { cn } from "@/lib/utils";
import { RelativeTime } from "@/components/common/relative-time";
import { stepVisual } from "@/components/runs/step-visuals";
import { Spinner } from "@/components/ui/spinner";
import { TONE_TEXT } from "@/lib/labels";
import type { RunStep } from "@/lib/types";

type PlannerTimelineProps = {
  steps: RunStep[];
  /** The planner is still working: pulse the newest step and show a "next step" row. */
  active: boolean;
};

/**
 * The planner's steps in plain language — a friendlier cousin of the full run trace. Icons
 * come from the tool used: a magnifier for searches, a globe for opening pages, a check for
 * validating a source.
 */
export function PlannerTimeline({ steps, active }: PlannerTimelineProps) {
  const ordered = [...steps].sort((a, b) => a.idx - b.idx);
  const latest = ordered.at(-1)?.idx;

  return (
    <ol
      aria-label="What the planner has done so far"
      className="relative space-y-0.5 before:absolute before:top-5 before:bottom-5 before:left-[1.625rem] before:w-px before:bg-border"
    >
      {ordered.map((step) => {
        const visual = stepVisual(step);
        const Icon = visual.icon;
        const isLatest = step.idx === latest;
        return (
          <li
            key={step.idx}
            className={cn("relative flex gap-3 rounded-lg px-3 py-2.5 transition-colors", isLatest && "bg-muted/60")}
          >
            <span
              className={cn(
                "relative z-10 flex size-7 shrink-0 items-center justify-center rounded-full border bg-background",
                TONE_TEXT[visual.tone],
                isLatest && active && "border-brand/40",
              )}
            >
              <Icon className="size-3.5" aria-hidden="true" />
              {isLatest && active ? (
                <span aria-hidden="true" className="absolute -top-0.5 -right-0.5 size-2 animate-pulse rounded-full bg-brand" />
              ) : null}
            </span>
            <div className="min-w-0 flex-1 pt-0.5">
              <p className={cn("text-sm leading-snug text-pretty", isLatest ? "font-medium" : "text-foreground/85")}>
                {step.summary}
              </p>
              <p className="mt-0.5 text-xs text-muted-foreground">
                {visual.label} · <RelativeTime value={step.created_at} />
              </p>
            </div>
          </li>
        );
      })}
      {active ? (
        <li className="relative flex items-center gap-3 px-3 py-2.5 text-sm text-muted-foreground">
          <span className="relative z-10 flex size-7 shrink-0 items-center justify-center rounded-full border border-dashed bg-background">
            <Spinner className="size-3.5" />
          </span>
          Deciding what to do next…
        </li>
      ) : null}
    </ol>
  );
}
