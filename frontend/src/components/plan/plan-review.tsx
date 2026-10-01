"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { mutate } from "swr";

import { MetaBadge } from "@/components/common/badges";
import { PageHeader } from "@/components/common/page-header";
import { RelativeTime } from "@/components/common/relative-time";
import { errorMessage } from "@/components/common/states";
import { api, paths } from "@/lib/api";
import { plural } from "@/lib/format";
import { revalidate } from "@/lib/hooks";
import { POLICY_STATUS } from "@/lib/labels";
import { routes } from "@/lib/routes";
import type { MonitoringPlan, PlanArea, PlanAttribute, PlanDetail, PlanEntity, PlanSource } from "@/lib/types";

import { AreasSection } from "./areas-section";
import { AttributesSection } from "./attributes-section";
import { EntitiesSection } from "./entities-section";
import { OpenQuestions, PlanOverview } from "./plan-overview";
import { countEdits, countEffective, specForApproval } from "./plan-spec";
import { RequestQuote } from "./request-quote";
import { ReviewActionBar } from "./review-action-bar";
import { SourcesSection } from "./sources-section";
import { useDraftAutosave } from "./use-draft-autosave";

const JUMP_LINKS = [
  { href: "#entities", label: "Entities" },
  { href: "#areas", label: "Areas" },
  { href: "#attributes", label: "Tracked values" },
  { href: "#sources", label: "Sources" },
];

type PlanReviewProps = {
  wid: string;
  plan: PlanDetail;
  /** The planner's proposal; edits are kept locally until approval. */
  initialSpec: MonitoringPlan;
};

/**
 * The first human-in-the-loop moment: review, adjust and approve (or reject) the monitoring
 * plan. Every edit is reversible, skipped items explain why, and nothing is monitored until
 * "Approve & start monitoring".
 */
export function PlanReview({ wid, plan, initialSpec }: PlanReviewProps) {
  const router = useRouter();
  const [original] = useState(initialSpec);
  const [spec, setSpec] = useState(initialSpec);
  const [busy, setBusy] = useState<"approve" | "reject" | null>(null);
  const draft = useDraftAutosave(wid, plan.id, spec);

  const counts = countEffective(spec);
  const edits = countEdits(original, spec);

  function edit(recipe: (current: MonitoringPlan) => MonitoringPlan) {
    draft.markDirty();
    setSpec(recipe);
  }

  const updateEntity = (ref: string, patch: Partial<PlanEntity>) =>
    edit((s) => ({ ...s, entities: s.entities.map((item) => (item.ref === ref ? { ...item, ...patch } : item)) }));
  const updateArea = (key: string, patch: Partial<PlanArea>) =>
    edit((s) => ({ ...s, areas: s.areas.map((item) => (item.key === key ? { ...item, ...patch } : item)) }));
  const updateAttribute = (position: number, patch: Partial<PlanAttribute>) =>
    edit((s) => ({ ...s, attributes: s.attributes.map((item, i) => (i === position ? { ...item, ...patch } : item)) }));
  const updateSource = (ref: string, patch: Partial<PlanSource>) =>
    edit((s) => ({ ...s, sources: s.sources.map((item) => (item.ref === ref ? { ...item, ...patch } : item)) }));

  function resetEdits() {
    const previous = spec;
    edit(() => original);
    toast("Restored the planner's proposal", {
      action: { label: "Undo", onClick: () => edit(() => previous) },
    });
  }

  async function approve() {
    setBusy("approve");
    draft.pause();
    try {
      const result = await api.plans.approve(wid, plan.id, { spec: specForApproval(spec) });
      toast.success("Monitoring started", {
        description: `${plural(result.sources_created, "source")} created and ${plural(result.jobs_enqueued, "baseline job")} queued. First observations become the baseline, so they never alert.`,
      });
      router.push(routes.dashboard(wid));
      // The sidebar (workspace status) stays mounted across navigation, so refresh it explicitly.
      void revalidate((path) => path === paths.workspace(wid) || path === paths.workspaces);
    } catch (error) {
      toast.error("Couldn't approve the plan", { description: errorMessage(error) });
      draft.resume();
      setBusy(null);
    }
  }

  async function reject() {
    setBusy("reject");
    draft.pause();
    try {
      const updated = await api.plans.reject(wid, plan.id);
      await mutate(paths.plan(wid, plan.id), updated, { revalidate: false });
      void revalidate((path) => path === paths.workspace(wid));
      toast("Plan rejected", { description: "Nothing from it will be monitored." });
    } catch (error) {
      toast.error("Couldn't reject the plan", { description: errorMessage(error) });
      draft.resume();
      setBusy(null);
    }
  }

  return (
    <div className="mx-auto max-w-5xl">
      <div className="space-y-10">
        <div className="space-y-6">
          <PageHeader
            eyebrow={
              <>
                <MetaBadge meta={POLICY_STATUS.pending_approval} tooltip={false} />
                <span className="text-xs text-muted-foreground">
                  Version {plan.version} · proposed <RelativeTime value={plan.created_at} />
                </span>
              </>
            }
            title="Review the monitoring plan"
            description="Nothing is monitored until you approve. Turn off anything that isn't useful, adjust how important each area is and how often sources are checked, then approve."
          />
          <RequestQuote text={plan.request_text} />
          <nav aria-label="Plan sections" className="flex flex-wrap gap-x-4 gap-y-1 text-sm">
            <span className="text-muted-foreground">Jump to</span>
            {JUMP_LINKS.map((link) => (
              <a key={link.href} href={link.href} className="font-medium text-brand underline-offset-4 hover:underline">
                {link.label}
              </a>
            ))}
          </nav>
        </div>

        <PlanOverview spec={spec} />
        <OpenQuestions questions={spec.open_questions} />
        <EntitiesSection spec={spec} onChange={updateEntity} />
        <AreasSection spec={spec} onChange={updateArea} />
        <AttributesSection spec={spec} onChange={updateAttribute} />
        <SourcesSection spec={spec} onChange={updateSource} />
      </div>

      <ReviewActionBar
        counts={counts}
        edits={edits}
        draft={draft.state}
        busy={busy}
        onResetEdits={resetEdits}
        onApprove={() => void approve()}
        onReject={() => void reject()}
      />
    </div>
  );
}
