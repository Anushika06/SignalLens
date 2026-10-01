"use client";

import { useEffect, useRef } from "react";
import { toast } from "sonner";

import { PageSkeleton } from "@/components/common/skeletons";
import { ErrorState } from "@/components/common/states";
import { paths } from "@/lib/api";
import { revalidate, usePlan } from "@/lib/hooks";
import type { PolicyStatus } from "@/lib/types";

import { PlanFailedView, PlanRejectedView, PlanSettledView } from "./plan-outcomes";
import { PlanReview } from "./plan-review";
import { PlanningView } from "./planning-view";

/**
 * /w/[wid]/plan/[pid] — one monitoring plan through its life: the planner at work
 * (`planning`, polled every 2 s), the human review (`pending_approval`), and its outcomes.
 */
export function PlanScreen({ wid, pid }: { wid: string; pid: string }) {
  const { data: plan, error, isLoading, mutate } = usePlan(wid, pid);
  const previousStatus = useRef<PolicyStatus | null>(null);

  // When planning finishes, say so and refresh the workspace status shown in the sidebar.
  useEffect(() => {
    const status = plan?.status ?? null;
    if (previousStatus.current === "planning" && status && status !== "planning") {
      if (status === "pending_approval") toast.success("Your monitoring plan is ready to review", { position: "top-center" });
      if (status === "failed") toast.error("The planner couldn't finish this plan");
      void revalidate((path) => path === paths.workspace(wid) || path === paths.workspaces);
    }
    previousStatus.current = status;
  }, [plan?.status, wid]);

  if (error && !plan) return <ErrorState error={error} onRetry={() => void mutate()} />;
  if (isLoading || !plan) return <PageSkeleton className="mx-auto max-w-4xl" />;

  switch (plan.status) {
    case "planning":
      return <PlanningView wid={wid} plan={plan} />;
    case "pending_approval":
      // A plan awaiting approval always carries a spec; until it arrives, keep showing the planner.
      return plan.spec ? (
        <PlanReview key={plan.id} wid={wid} plan={plan} initialSpec={plan.spec} />
      ) : (
        <PlanningView wid={wid} plan={plan} />
      );
    case "failed":
      return <PlanFailedView wid={wid} plan={plan} />;
    case "rejected":
      return <PlanRejectedView wid={wid} plan={plan} />;
    case "active":
    case "superseded":
    default:
      return <PlanSettledView wid={wid} plan={plan} />;
  }
}
