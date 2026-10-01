"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Bot } from "lucide-react";

import { PageHeader } from "@/components/common/page-header";
import { RelativeTime, useTick } from "@/components/common/relative-time";
import { TableSkeleton } from "@/components/common/skeletons";
import { EmptyState, ErrorState } from "@/components/common/states";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { durationBetween, formatCompact, formatDuration, formatNumber, formatUsd, plural } from "@/lib/format";
import { isRunActive, useRuns } from "@/lib/hooks";
import { AGENT } from "@/lib/labels";
import { routes } from "@/lib/routes";
import type { AgentName, RunSummary } from "@/lib/types";

import { AgentIcon, isAgentName } from "./agent-icon";
import { RunStatusBadge } from "./run-status-badge";
import { RUN_SUBJECT_LABEL } from "./run-subject";
import { UsageInline } from "./run-usage";

const RUNS_LIMIT = 50;
const ALL_AGENTS = "all";
const AGENT_NAMES = Object.keys(AGENT) as AgentName[];

function runDuration(run: RunSummary) {
  return formatDuration(durationBetween(run.started_at, run.finished_at));
}

function AgentFilter({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  return (
    <div className="flex items-center gap-2">
      <Label htmlFor="agent-filter" className="text-sm text-muted-foreground">
        Agent
      </Label>
      <Select value={value} onValueChange={onChange}>
        <SelectTrigger id="agent-filter" className="min-w-40">
          <SelectValue />
        </SelectTrigger>
        <SelectContent position="popper" align="end">
          <SelectItem value={ALL_AGENTS}>All agents</SelectItem>
          {AGENT_NAMES.map((name) => (
            <SelectItem key={name} value={name}>
              {AGENT[name].label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}

/** Runs as a table from `sm` up; each row links to the full trace. */
function RunsTable({ wid, runs }: { wid: string; runs: RunSummary[] }) {
  useTick(); // keeps "running" durations moving between polls
  return (
    <div className="hidden overflow-hidden rounded-xl border bg-card sm:block">
      <Table>
        <TableHeader>
          <TableRow className="bg-muted/40 hover:bg-muted/40">
            <TableHead className="pl-4">Run</TableHead>
            <TableHead>Status</TableHead>
            <TableHead>Started</TableHead>
            <TableHead className="text-right">Duration</TableHead>
            <TableHead className="text-right">Model calls</TableHead>
            <TableHead className="text-right">Tool calls</TableHead>
            <TableHead className="text-right">Tokens</TableHead>
            <TableHead className="pr-4 text-right">Est. cost</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {runs.map((run) => (
            <TableRow key={run.id}>
              <TableCell className="max-w-[26rem] py-2.5 pl-4">
                <div className="flex items-center gap-3">
                  <AgentIcon agent={run.agent} />
                  <div className="min-w-0">
                    <Link
                      href={routes.run(wid, run.id)}
                      className="block truncate font-medium underline-offset-4 hover:text-brand hover:underline"
                    >
                      {run.title}
                    </Link>
                    <p className="truncate text-xs text-muted-foreground">
                      {AGENT[run.agent].label}
                      {run.subject ? ` · ${RUN_SUBJECT_LABEL[run.subject.type]}` : ""}
                    </p>
                  </div>
                </div>
              </TableCell>
              <TableCell>
                <RunStatusBadge status={run.status} />
              </TableCell>
              <TableCell className="text-muted-foreground">
                <RelativeTime value={run.started_at} />
              </TableCell>
              <TableCell className="metric text-right">{runDuration(run)}</TableCell>
              <TableCell className="metric text-right">{formatNumber(run.usage.llm_calls)}</TableCell>
              <TableCell className="metric text-right">{formatNumber(run.usage.tool_calls)}</TableCell>
              <TableCell className="metric text-right">
                {formatCompact(run.usage.input_tokens + run.usage.output_tokens)}
              </TableCell>
              <TableCell className="metric pr-4 text-right">{formatUsd(run.usage.est_cost_usd)}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

/** The same runs as stacked cards on phones. */
function RunsCards({ wid, runs }: { wid: string; runs: RunSummary[] }) {
  return (
    <ul className="space-y-2 sm:hidden">
      {runs.map((run) => (
        <li key={run.id} className="relative rounded-xl border bg-card p-3 has-[a:focus-visible]:ring-3 has-[a:focus-visible]:ring-ring/50">
          <div className="flex items-start gap-3">
            <AgentIcon agent={run.agent} />
            <div className="min-w-0 flex-1 space-y-1.5">
              <Link
                href={routes.run(wid, run.id)}
                className="line-clamp-2 text-sm font-medium after:absolute after:inset-0 focus-visible:outline-none"
              >
                {run.title}
              </Link>
              <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
                <RunStatusBadge status={run.status} />
                <span>{AGENT[run.agent].label}</span>
                <span aria-hidden="true">·</span>
                <RelativeTime value={run.started_at} />
                <span aria-hidden="true">·</span>
                <span className="metric">{runDuration(run)}</span>
              </div>
              <UsageInline usage={run.usage} />
            </div>
          </div>
        </li>
      ))}
    </ul>
  );
}

/** All agent runs in the workspace — the "show your work" log. */
export function RunsScreen({ wid }: { wid: string }) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const agentParam = searchParams.get("agent");
  const agent = isAgentName(agentParam) ? agentParam : undefined;
  const { data: runs, error, isLoading, mutate } = useRuns(wid, { agent, limit: RUNS_LIMIT });

  function setAgent(value: string) {
    const params = new URLSearchParams(searchParams.toString());
    if (value === ALL_AGENTS) params.delete("agent");
    else params.set("agent", value);
    const query = params.toString();
    router.replace(query ? `${pathname}?${query}` : pathname, { scroll: false });
  }

  const running = runs?.filter((run) => isRunActive(run.status)).length ?? 0;
  const totalCost = runs?.reduce((sum, run) => sum + run.usage.est_cost_usd, 0) ?? 0;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Agent runs"
        description="Every model call and tool call an agent makes is recorded as a step of a run — so you can check its work: what it searched, what it read, what it concluded and what it cost."
        actions={<AgentFilter value={agent ?? ALL_AGENTS} onChange={setAgent} />}
      />

      {error && !runs ? (
        <ErrorState error={error} onRetry={() => void mutate()} />
      ) : isLoading || !runs ? (
        <TableSkeleton rows={8} columns={6} />
      ) : runs.length === 0 ? (
        agent ? (
          <EmptyState
            icon={Bot}
            title={`No ${AGENT[agent].label.toLowerCase()} runs yet`}
            description={`${AGENT[agent].description ?? ""} Its runs will appear here, with every step recorded.`}
            action={
              <Button variant="outline" size="sm" onClick={() => setAgent(ALL_AGENTS)}>
                Show all agents
              </Button>
            }
          />
        ) : (
          <EmptyState
            icon={Bot}
            title="No agent runs yet"
            description="Runs appear when the planner researches a monitoring request and when a material change is investigated and analysed. Each run records every step, so you can see exactly how a conclusion was reached."
          />
        )
      ) : (
        <div className="space-y-3">
          <p className="metric text-sm text-muted-foreground">
            {runs.length >= RUNS_LIMIT ? `Latest ${plural(runs.length, "run")}` : plural(runs.length, "run")}
            {running > 0 ? ` · ${running} in progress` : ""} · {formatUsd(totalCost)} estimated cost
          </p>
          <RunsTable wid={wid} runs={runs} />
          <RunsCards wid={wid} runs={runs} />
        </div>
      )}
    </div>
  );
}
