"use client";

import { useState } from "react";
import { ListTree } from "lucide-react";

import { Section } from "@/components/common/page-header";
import { EmptyState } from "@/components/common/states";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { STEP_KIND } from "@/lib/labels";
import type { RunStatus, RunStep, StepKind } from "@/lib/types";

import { RunTrace } from "./run-trace";

/** Display order for the kind filter: the story of a run, then the safety rails. */
const KIND_ORDER: StepKind[] = [
  "decision",
  "tool_call",
  "observation",
  "llm_call",
  "state_update",
  "note",
  "guardrail",
  "error",
];

type Filter = StepKind | "all";

type RunStepsPanelProps = {
  steps: RunStep[];
  status: RunStatus;
};

/**
 * The run's steps as a timeline, with chips to focus on one kind of step (e.g. only tool
 * calls, or only guardrails — where the agent was stopped from doing something unsafe).
 */
export function RunStepsPanel({ steps, status }: RunStepsPanelProps) {
  const [filter, setFilter] = useState<Filter>("all");
  const live = status === "running" || status === "queued";

  const counts = new Map<StepKind, number>();
  for (const step of steps) counts.set(step.kind, (counts.get(step.kind) ?? 0) + 1);
  const kinds = KIND_ORDER.filter((kind) => counts.has(kind));
  const visible = filter === "all" ? steps : steps.filter((step) => step.kind === filter);

  return (
    <Section
      id="steps"
      title={`Steps (${steps.length})`}
      description="Each decision, tool call, model call and guardrail, in order. Expand a step to see its raw input and output."
    >
      {kinds.length > 1 ? (
        <ToggleGroup
          type="single"
          variant="outline"
          size="sm"
          spacing={1}
          value={filter}
          onValueChange={(value) => setFilter((value || "all") as Filter)}
          aria-label="Show steps of one kind"
          className="w-full flex-wrap"
        >
          <ToggleGroupItem value="all">
            All <span className="metric text-muted-foreground">{steps.length}</span>
          </ToggleGroupItem>
          {kinds.map((kind) => {
            const Icon = STEP_KIND[kind].icon;
            return (
              <ToggleGroupItem key={kind} value={kind}>
                {Icon ? <Icon aria-hidden="true" /> : null}
                {STEP_KIND[kind].label}
                <span className="metric text-muted-foreground">{counts.get(kind)}</span>
              </ToggleGroupItem>
            );
          })}
        </ToggleGroup>
      ) : null}

      {steps.length === 0 && !live ? (
        <EmptyState
          icon={ListTree}
          title="No steps recorded"
          description="This run finished without recording any steps."
        />
      ) : status === "queued" && steps.length === 0 ? (
        <p className="rounded-xl border border-dashed px-4 py-6 text-center text-sm text-muted-foreground">
          Queued — the run will start as soon as a worker picks it up. Steps appear here live.
        </p>
      ) : (
        <RunTrace steps={visible} live={live && filter === "all"} />
      )}
    </Section>
  );
}
