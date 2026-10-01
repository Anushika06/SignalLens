import { Check } from "lucide-react";

import { cn } from "@/lib/utils";

type StepIndicatorProps = {
  steps: string[];
  /** Zero-based index of the current step. */
  current: number;
  /** Lets the user go back to a completed step. */
  onSelect?: (index: number) => void;
};

/** Numbered progress for the onboarding wizard ("1 Your company — 2 What to monitor"). */
export function StepIndicator({ steps, current, onSelect }: StepIndicatorProps) {
  return (
    <nav aria-label="Setup progress">
      <ol className="flex flex-wrap items-center gap-x-3 gap-y-2">
        {steps.map((label, index) => {
          const state = index < current ? "done" : index === current ? "current" : "upcoming";
          const content = (
            <>
              <span
                aria-hidden="true"
                className={cn(
                  "metric flex size-6 shrink-0 items-center justify-center rounded-full border text-xs font-medium",
                  state === "done" && "border-primary bg-primary text-primary-foreground",
                  state === "current" && "border-primary text-brand",
                  state === "upcoming" && "text-muted-foreground",
                )}
              >
                {state === "done" ? <Check className="size-3.5" /> : index + 1}
              </span>
              <span className={cn("text-sm", state === "current" ? "font-medium" : "text-muted-foreground")}>
                <span className="sr-only">Step {index + 1}: </span>
                {label}
                {state === "done" ? <span className="sr-only"> (done)</span> : null}
              </span>
            </>
          );
          return (
            <li key={label} className="flex items-center gap-3" aria-current={state === "current" ? "step" : undefined}>
              {index > 0 ? <span aria-hidden="true" className="h-px w-6 bg-border sm:w-10" /> : null}
              {state === "done" && onSelect ? (
                <button
                  type="button"
                  onClick={() => onSelect(index)}
                  className="flex items-center gap-2 rounded-md hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none"
                >
                  {content}
                </button>
              ) : (
                <span className="flex items-center gap-2">{content}</span>
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
