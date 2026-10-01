"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ClipboardCheck, Database, type LucideIcon, PauseCircle, Sparkles, UserCheck } from "lucide-react";
import { toast } from "sonner";

import { cn } from "@/lib/utils";
import { errorMessage } from "@/components/common/states";
import { Button } from "@/components/ui/button";
import { Field, FieldLabel } from "@/components/ui/field";
import { Spinner } from "@/components/ui/spinner";
import { Textarea } from "@/components/ui/textarea";
import { api, paths } from "@/lib/api";
import { plural } from "@/lib/format";
import { revalidate } from "@/lib/hooks";
import { routes } from "@/lib/routes";
import type { WorkspaceDetail } from "@/lib/types";

type CalloutProps = {
  icon: LucideIcon;
  tone: "brand" | "amber" | "gray";
  title: string;
  children: React.ReactNode;
  action?: React.ReactNode;
  busy?: boolean;
};

const CALLOUT_TONE = {
  brand: "border-brand/20 bg-brand/5 [&_[data-icon]]:text-brand",
  amber:
    "border-amber-200 bg-amber-50 dark:border-amber-500/25 dark:bg-amber-500/10 [&_[data-icon]]:text-amber-600 dark:[&_[data-icon]]:text-amber-400",
  gray: "bg-muted/50 [&_[data-icon]]:text-muted-foreground",
} as const;

function Callout({ icon: Icon, tone, title, children, action, busy }: CalloutProps) {
  return (
    <div
      role="status"
      className={cn("flex flex-col gap-3 rounded-xl border p-4 sm:flex-row sm:items-center", CALLOUT_TONE[tone])}
    >
      <div className="flex min-w-0 flex-1 gap-3">
        <span data-icon className="mt-0.5 shrink-0">
          {busy ? <Spinner className="size-5" /> : <Icon className="size-5" aria-hidden="true" />}
        </span>
        <div className="min-w-0 space-y-0.5">
          <p className="text-sm font-medium">{title}</p>
          <div className="text-sm text-pretty text-muted-foreground">{children}</div>
        </div>
      </div>
      {action ? <div className="flex shrink-0 gap-2 pl-8 sm:pl-0">{action}</div> : null}
    </div>
  );
}

/** For a workspace with no plan yet: ask what to monitor, right here. */
function StartPlan({ wid }: { wid: string }) {
  const router = useRouter();
  const [text, setText] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!text.trim()) return;
    setSubmitting(true);
    try {
      const plan = await api.plans.create(wid, { request_text: text.trim() });
      await revalidate(paths.workspace(wid));
      router.push(routes.plan(wid, plan.id));
    } catch (error) {
      toast.error("Couldn't start the planner", { description: errorMessage(error) });
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={submit} className="space-y-3 rounded-xl border bg-card p-4">
      <Field>
        <FieldLabel htmlFor="start-plan">What should SignalLens monitor?</FieldLabel>
        <Textarea
          id="start-plan"
          value={text}
          onChange={(event) => setText(event.target.value)}
          placeholder="I want to monitor Razorpay's pricing, partnerships and regulatory developments."
          rows={3}
        />
      </Field>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-xs text-pretty text-muted-foreground">
          The planner researches the request and proposes sources for you to approve. Nothing is monitored until you
          do.
        </p>
        <Button type="submit" disabled={!text.trim() || submitting}>
          {submitting ? <Spinner /> : <Sparkles aria-hidden="true" />}
          Research &amp; propose a plan
        </Button>
      </div>
    </form>
  );
}

type WorkspaceCalloutsProps = {
  wid: string;
  workspace: WorkspaceDetail;
  pendingApprovals: number;
};

/** Anything that needs the user's attention before the dashboard itself. */
export function WorkspaceCallouts({ wid, workspace, pendingApprovals }: WorkspaceCalloutsProps) {
  const { status, pending_policy_id: pendingPlan, active_policy_id: activePlan } = workspace;
  const callouts: React.ReactNode[] = [];

  if (pendingPlan && status === "planning") {
    callouts.push(
      <Callout
        key="planning"
        icon={Sparkles}
        tone="brand"
        busy
        title="SignalLens is researching your request"
        action={
          <Button asChild size="sm" variant="outline">
            <Link href={routes.plan(wid, pendingPlan)}>Watch the agent</Link>
          </Button>
        }
      >
        It is reading official sites and recent news to propose what to monitor. You&apos;ll review the plan before
        anything starts.
      </Callout>,
    );
  } else if (pendingPlan && status === "awaiting_approval") {
    callouts.push(
      <Callout
        key="review"
        icon={ClipboardCheck}
        tone="amber"
        title="Your monitoring plan is ready for review"
        action={
          <Button asChild size="sm">
            <Link href={routes.plan(wid, pendingPlan)}>Review plan</Link>
          </Button>
        }
      >
        Check the entities, sources and areas the agent proposes. Nothing is monitored until you approve it.
      </Callout>,
    );
  } else if (pendingPlan && activePlan) {
    callouts.push(
      <Callout
        key="revision"
        icon={ClipboardCheck}
        tone="brand"
        title="A revised monitoring plan is in progress"
        action={
          <Button asChild size="sm" variant="outline">
            <Link href={routes.plan(wid, pendingPlan)}>Open plan</Link>
          </Button>
        }
      >
        Monitoring continues on the current plan until you approve the new one.
      </Callout>,
    );
  }

  if (status === "baselining") {
    callouts.push(
      <Callout key="baseline" icon={Database} tone="brand" busy title="Building the baseline">
        First snapshots become the baseline and never raise alerts. Official pages are also replayed from the web
        archive, so historical changes appear here within minutes.
      </Callout>,
    );
  }

  if (status === "paused") {
    callouts.push(
      <Callout key="paused" icon={PauseCircle} tone="gray" title="Monitoring is paused">
        Sources are not being checked. Existing intelligence and the world state remain available.
      </Callout>,
    );
  }

  if (pendingApprovals > 0) {
    callouts.push(
      <Callout
        key="approvals"
        icon={UserCheck}
        tone="amber"
        title={`${plural(pendingApprovals, "action")} waiting for your decision`}
        action={
          <Button asChild size="sm" variant="outline">
            <Link href={routes.approvals(wid)}>Review</Link>
          </Button>
        }
      >
        SignalLens never emails, shares or posts outside your company without a human decision.
      </Callout>,
    );
  }

  if (status === "setup" && !pendingPlan && !activePlan) {
    callouts.push(<StartPlan key="start" wid={wid} />);
  }

  if (callouts.length === 0) return null;
  return <div className="space-y-3">{callouts}</div>;
}
