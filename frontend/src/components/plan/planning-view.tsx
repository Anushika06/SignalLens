"use client";

import Link from "next/link";
import { ArrowUpRight } from "lucide-react";

import { MetaBadge } from "@/components/common/badges";
import { PageHeader, Section } from "@/components/common/page-header";
import { Stat, StatGrid } from "@/components/common/stat";
import { stepVisual } from "@/components/runs/step-visuals";
import { Card, CardContent } from "@/components/ui/card";
import { Spinner } from "@/components/ui/spinner";
import { durationBetween, formatDuration, formatNumber } from "@/lib/format";
import { isRunActive, useRun } from "@/lib/hooks";
import { POLICY_STATUS } from "@/lib/labels";
import { routes } from "@/lib/routes";
import type { PlanDetail, RunDetail } from "@/lib/types";

import { PlannerTimeline } from "./planner-timeline";
import { RequestQuote } from "./request-quote";
import { useElapsed } from "./use-elapsed";

/** One line describing what the planner is doing right now. */
function currentActivity(plan: PlanDetail, run: RunDetail | undefined): string {
  if (!plan.run_id) return "Waiting for the planner to start…";
  if (!run) return "Connecting to the planner…";
  if (run.status === "queued") return "Queued — waiting for a worker to pick this up.";
  if (run.status === "failed" || run.status === "budget_exhausted") {
    return run.error ? `The planner stopped: ${run.error}` : "The planner stopped before finishing.";
  }
  if (run.status === "succeeded") return "Research is done. Putting the plan together…";
  const latest = [...run.steps].sort((a, b) => b.idx - a.idx)[0];
  return latest?.summary ?? "Starting research…";
}

/**
 * Shown while the plan is `planning`: the planner's run, live. Progress is reported as facts
 * (time elapsed, steps taken, sources validated) — never as a guessed percentage.
 */
export function PlanningView({ wid, plan }: { wid: string; plan: PlanDetail }) {
  // `live`: keep polling while the plan is planning, even if the run is not created yet.
  const { data: run } = useRun(wid, plan.run_id, { live: plan.status === "planning" });
  const steps = run?.steps ?? [];
  const running = !run || isRunActive(run.status);
  const startedAt = run?.started_at ?? plan.created_at;
  const liveElapsed = useElapsed(startedAt, running);
  const elapsed = run?.finished_at ? durationBetween(startedAt, run.finished_at) : liveElapsed;
  const validated = steps.filter((step) => step.kind === "tool_call" && stepVisual(step).label === "Validation").length;

  return (
    <div className="mx-auto max-w-3xl space-y-8">
      <PageHeader
        eyebrow={
          <>
            <MetaBadge meta={POLICY_STATUS.planning} tooltip={false} />
            <span className="text-xs text-muted-foreground">Plan version {plan.version}</span>
          </>
        }
        title="Researching your request"
        description="The planner is working out what to monitor: the entities involved, the areas that matter and the sources worth watching. You review everything before anything is monitored."
      />

      <RequestQuote text={plan.request_text} />

      <Card>
        <CardContent className="space-y-5">
          <div className="flex items-start gap-3">
            {running ? (
              <Spinner className="mt-0.5 shrink-0 text-brand" />
            ) : (
              <span aria-hidden="true" className="mt-1.5 size-2 shrink-0 rounded-full bg-brand" />
            )}
            <div className="min-w-0 space-y-0.5">
              <p className="text-xs font-medium text-muted-foreground">Now</p>
              <p className="text-sm font-medium text-pretty" aria-live="polite">
                {currentActivity(plan, run)}
              </p>
            </div>
          </div>
          <StatGrid className="grid-cols-2 border-t pt-4 sm:grid-cols-4">
            <Stat label="Elapsed" value={elapsed === null ? "—" : formatDuration(elapsed)} />
            <Stat label="Steps taken" value={formatNumber(steps.length)} />
            <Stat label="Searches & page reads" value={formatNumber(run?.usage.tool_calls ?? 0)} />
            <Stat label="Sources validated" value={formatNumber(validated)} />
          </StatGrid>
        </CardContent>
      </Card>

      <Section
        id="planner-steps"
        title="What the planner has done"
        description="Every search, page and check is recorded, so you can see how the plan was built."
        actions={
          plan.run_id ? (
            <Link
              href={routes.run(wid, plan.run_id)}
              className="inline-flex items-center gap-1 text-sm font-medium text-brand underline-offset-4 hover:underline"
            >
              Full trace
              <ArrowUpRight className="size-3.5" aria-hidden="true" />
            </Link>
          ) : null
        }
      >
        {steps.length > 0 ? (
          <PlannerTimeline steps={steps} active={running} />
        ) : (
          <div className="flex items-center gap-3 rounded-xl border border-dashed px-4 py-6 text-sm text-muted-foreground">
            <Spinner className="shrink-0" />
            The first steps will appear here as soon as the planner starts.
          </div>
        )}
      </Section>

      <p className="rounded-xl border bg-muted/30 p-4 text-sm text-pretty text-muted-foreground">
        You can leave this page — the planner keeps working, and the plan will be waiting on this workspace for your
        review. Nothing is monitored until you approve it.
      </p>
    </div>
  );
}
