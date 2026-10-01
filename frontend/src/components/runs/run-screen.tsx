"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { AlertTriangle, ArrowLeft, ArrowUpRight, ChevronDown, Gauge } from "lucide-react";

import { PageHeader } from "@/components/common/page-header";
import { JsonView } from "@/components/common/json-view";
import { RelativeTime } from "@/components/common/relative-time";
import { PageSkeleton } from "@/components/common/skeletons";
import { Stat, StatGrid } from "@/components/common/stat";
import { ErrorState } from "@/components/common/states";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { durationBetween, formatDateTime, formatDuration, formatNumber, formatUsd } from "@/lib/format";
import { isRunActive, useRun } from "@/lib/hooks";
import { AGENT } from "@/lib/labels";
import { routes } from "@/lib/routes";
import type { RunDetail } from "@/lib/types";

import { AgentIcon } from "./agent-icon";
import { exhaustedLimits, RunBudget } from "./run-budget";
import { RunStatusBadge } from "./run-status-badge";
import { RunStepsPanel } from "./run-steps-panel";
import { RUN_SUBJECT_LABEL, runSubjectHref } from "./run-subject";

/** Re-render every second while `active`, so elapsed time counts up between polls. */
function useSecondTicker(active: boolean) {
  const [, setTick] = useState(0);
  useEffect(() => {
    if (!active) return;
    const id = setInterval(() => setTick((tick) => tick + 1), 1000);
    return () => clearInterval(id);
  }, [active]);
}

function BackToRuns({ wid }: { wid: string }) {
  return (
    <Button asChild variant="ghost" size="sm" className="-ml-2 text-muted-foreground">
      <Link href={routes.runs(wid)}>
        <ArrowLeft aria-hidden="true" />
        All runs
      </Link>
    </Button>
  );
}

function TimeFacts({ run }: { run: RunDetail }) {
  const active = isRunActive(run.status);
  const duration = durationBetween(run.started_at, run.finished_at);
  const items = [
    {
      label: "Started",
      value: run.started_at ? (
        <>
          {formatDateTime(run.started_at)} <span className="text-muted-foreground">(<RelativeTime value={run.started_at} />)</span>
        </>
      ) : (
        "Not yet"
      ),
    },
    {
      label: "Finished",
      value: run.finished_at ? <RelativeTime value={run.finished_at} /> : active ? "In progress" : "—",
    },
    { label: active ? "Running for" : "Duration", value: <span className="metric">{formatDuration(duration)}</span> },
  ];
  return (
    <dl className="flex flex-wrap gap-x-8 gap-y-2 text-sm">
      {items.map((item) => (
        <div key={item.label} className="space-y-0.5">
          <dt className="text-xs text-muted-foreground">{item.label}</dt>
          <dd>{item.value}</dd>
        </div>
      ))}
    </dl>
  );
}

function JsonDisclosure({ title, description, value, empty }: { title: string; description: string; value: unknown; empty: string }) {
  const hasValue = value !== null && value !== undefined;
  return (
    <Collapsible className="rounded-xl border bg-card">
      <CollapsibleTrigger className="group flex w-full items-center justify-between gap-3 rounded-xl px-4 py-3 text-left outline-none focus-visible:ring-3 focus-visible:ring-ring/50">
        <span className="min-w-0">
          <span className="block text-sm font-medium">{title}</span>
          <span className="block text-xs text-muted-foreground">{description}</span>
        </span>
        <ChevronDown
          className="size-4 shrink-0 text-muted-foreground transition-transform group-data-[state=open]:rotate-180"
          aria-hidden="true"
        />
      </CollapsibleTrigger>
      <CollapsibleContent className="px-4 pb-4">
        {hasValue ? <JsonView value={value} label={title} /> : <p className="text-sm text-muted-foreground">{empty}</p>}
      </CollapsibleContent>
    </Collapsible>
  );
}

function RunDetailView({ wid, run }: { wid: string; run: RunDetail }) {
  const active = isRunActive(run.status);
  useSecondTicker(active);
  const subjectHref = runSubjectHref(wid, run.subject);
  const limits = run.status === "budget_exhausted" ? exhaustedLimits(run) : [];
  const agent = AGENT[run.agent];

  return (
    <div className="space-y-8">
      <div className="space-y-4">
        <BackToRuns wid={wid} />
        <PageHeader
          eyebrow={
            <>
              <AgentIcon agent={run.agent} className="size-6 rounded-md [&_svg]:size-3.5" />
              <span className="text-sm font-medium">{agent.label}</span>
              <RunStatusBadge status={run.status} />
            </>
          }
          title={run.title}
          description={agent.description}
          actions={
            subjectHref && run.subject ? (
              <Button asChild variant="outline" size="sm">
                <Link href={subjectHref}>
                  Open {RUN_SUBJECT_LABEL[run.subject.type].toLowerCase()}
                  <ArrowUpRight aria-hidden="true" />
                </Link>
              </Button>
            ) : null
          }
        />
        <TimeFacts run={run} />
      </div>

      {run.error ? (
        <Alert variant="destructive">
          <AlertTriangle aria-hidden="true" />
          <AlertTitle>The run failed</AlertTitle>
          <AlertDescription className="whitespace-pre-line">{run.error}</AlertDescription>
        </Alert>
      ) : null}

      {run.status === "budget_exhausted" ? (
        <Alert className="border-amber-200 bg-amber-50 text-amber-900 dark:border-amber-500/25 dark:bg-amber-500/10 dark:text-amber-200">
          <Gauge aria-hidden="true" />
          <AlertTitle>Stopped at a hard limit{limits.length ? ` (${limits.join(", ")})` : ""}</AlertTitle>
          <AlertDescription className="text-amber-900/80 dark:text-amber-200/80">
            Every run has fixed budgets for steps, tool calls, time and cost, so an investigation can never run away.
            The steps below show everything the agent did before it stopped.
          </AlertDescription>
        </Alert>
      ) : null}

      <div className="grid gap-4 lg:grid-cols-5">
        <Card className="lg:col-span-3">
          <CardHeader>
            <CardTitle>Usage</CardTitle>
            <CardDescription>What this run consumed{active ? " so far" : ""}.</CardDescription>
          </CardHeader>
          <CardContent>
            <StatGrid className="grid-cols-2 sm:grid-cols-3">
              <Stat label="Model calls" value={formatNumber(run.usage.llm_calls)} />
              <Stat label="Tool calls" value={formatNumber(run.usage.tool_calls)} />
              <Stat label="Est. cost" value={formatUsd(run.usage.est_cost_usd)} />
              <Stat label="Input tokens" value={formatNumber(run.usage.input_tokens)} />
              <Stat label="Output tokens" value={formatNumber(run.usage.output_tokens)} />
              <Stat label="Steps" value={formatNumber(run.steps.length)} />
            </StatGrid>
          </CardContent>
        </Card>
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Budget</CardTitle>
            <CardDescription>Hard limits. The agent stops when it reaches any of them.</CardDescription>
          </CardHeader>
          <CardContent>
            <RunBudget run={run} />
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-3 lg:grid-cols-2">
        <JsonDisclosure
          title="Task"
          description="What the agent was asked to do"
          value={run.task}
          empty="No task recorded."
        />
        <JsonDisclosure
          title="Result"
          description="What the agent concluded"
          value={run.result}
          empty={active ? "Available when the run finishes." : "This run produced no result."}
        />
      </div>

      <RunStepsPanel steps={run.steps} status={run.status} />
    </div>
  );
}

/** One agent run, step by step — the "show your work" trace. Polls every 2 s while running. */
export function RunScreen({ wid, runId }: { wid: string; runId: string }) {
  const { data: run, error, isLoading, mutate } = useRun(wid, runId);

  if (error && !run) {
    return (
      <div className="space-y-4">
        <BackToRuns wid={wid} />
        <ErrorState
          error={error}
          title={error.status === 404 ? "This run doesn't exist" : undefined}
          onRetry={() => void mutate()}
        />
      </div>
    );
  }
  if (isLoading || !run) return <PageSkeleton />;
  return <RunDetailView wid={wid} run={run} />;
}
