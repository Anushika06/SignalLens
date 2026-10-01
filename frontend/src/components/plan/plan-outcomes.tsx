import Link from "next/link";
import { AlertTriangle, ArrowUpRight } from "lucide-react";

import { MetaBadge } from "@/components/common/badges";
import { PageHeader, Section, TextBlock } from "@/components/common/page-header";
import { Stat, StatGrid } from "@/components/common/stat";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { formatDateTime, formatNumber } from "@/lib/format";
import { POLICY_STATUS } from "@/lib/labels";
import { routes } from "@/lib/routes";
import type { PlanDetail } from "@/lib/types";

import { NewPlanForm } from "./new-plan-form";
import { countEffective } from "./plan-spec";
import { RequestQuote } from "./request-quote";

type OutcomeProps = { wid: string; plan: PlanDetail };

function TraceLink({ wid, runId, children }: { wid: string; runId: string | null; children: React.ReactNode }) {
  if (!runId) return null;
  return (
    <Link
      href={routes.run(wid, runId)}
      className="inline-flex items-center gap-1 text-sm font-medium text-brand underline-offset-4 hover:underline"
    >
      {children}
      <ArrowUpRight className="size-3.5" aria-hidden="true" />
    </Link>
  );
}

/** The planner gave up: show why, and let the user retry with the same (or an edited) request. */
export function PlanFailedView({ wid, plan }: OutcomeProps) {
  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <PageHeader
        eyebrow={<MetaBadge meta={POLICY_STATUS.failed} tooltip={false} />}
        title="The planner couldn't finish this plan"
        description="Nothing is being monitored from this request. Adjust it if you like, then try again."
      />
      <RequestQuote text={plan.request_text} />
      <Alert variant="destructive">
        <AlertTriangle aria-hidden="true" />
        <AlertTitle>What went wrong</AlertTitle>
        <AlertDescription>{plan.error ?? "The planner stopped without recording a reason."}</AlertDescription>
      </Alert>
      <TraceLink wid={wid} runId={plan.run_id}>
        See what the planner did before it stopped
      </TraceLink>
      <Section title="Try again" description="This starts a new planner run in the same workspace.">
        <NewPlanForm
          wid={wid}
          initialText={plan.request_text}
          submitLabel="Retry planning"
          hint="Naming the company precisely (and its country) helps the planner find the right entity."
        />
      </Section>
    </div>
  );
}

/** The user rejected the plan: nothing is monitored; offer a fresh start. */
export function PlanRejectedView({ wid, plan }: OutcomeProps) {
  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <PageHeader
        eyebrow={<MetaBadge meta={POLICY_STATUS.rejected} tooltip={false} />}
        title="You rejected this plan"
        description="SignalLens isn't monitoring anything from it. Refine the request and the planner will research again."
      />
      <RequestQuote text={plan.request_text} />
      <Section title="Start a new plan">
        <NewPlanForm
          wid={wid}
          initialText={plan.request_text}
          submitLabel="Start a new plan"
          hint="Say what was wrong with the last plan, e.g. “Focus on pricing and RBI regulation only.”"
        />
      </Section>
      <Button asChild variant="ghost">
        <Link href={routes.dashboard(wid)}>Back to the dashboard</Link>
      </Button>
    </div>
  );
}

/** An approved (active) or replaced (superseded) plan — read-only. */
export function PlanSettledView({ wid, plan }: OutcomeProps) {
  const active = plan.status === "active";
  const counts = plan.spec ? countEffective(plan.spec) : null;
  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <PageHeader
        eyebrow={
          <>
            <MetaBadge meta={POLICY_STATUS[plan.status]} tooltip={false} />
            <span className="text-xs text-muted-foreground">Version {plan.version}</span>
          </>
        }
        title={active ? "This plan is active" : "This plan was replaced by a newer version"}
        description={
          active
            ? `Approved ${formatDateTime(plan.approved_at)}. SignalLens is monitoring everything it covers.`
            : "It is kept for reference. The current plan is on the Monitoring page."
        }
        actions={
          active ? (
            <>
              <Button asChild variant="outline">
                <Link href={routes.monitoring(wid)}>Monitoring settings</Link>
              </Button>
              <Button asChild>
                <Link href={routes.dashboard(wid)}>Open the dashboard</Link>
              </Button>
            </>
          ) : (
            <Button asChild>
              <Link href={routes.monitoring(wid)}>See the current plan</Link>
            </Button>
          )
        }
      />
      <RequestQuote text={plan.request_text} />
      {plan.spec && counts ? (
        <Card>
          <CardContent className="space-y-5">
            <TextBlock text={plan.spec.summary} />
            <StatGrid className="grid-cols-2 border-t pt-4 sm:grid-cols-4">
              <Stat label="Entities" value={formatNumber(counts.entities)} />
              <Stat label="Areas" value={formatNumber(counts.areas)} />
              <Stat label="Sources" value={formatNumber(counts.sources)} />
              <Stat label="Tracked values" value={formatNumber(counts.attributes)} />
            </StatGrid>
          </CardContent>
        </Card>
      ) : null}
      <TraceLink wid={wid} runId={plan.run_id}>
        How the planner built this plan
      </TraceLink>
    </div>
  );
}
