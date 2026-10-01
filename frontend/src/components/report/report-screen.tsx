"use client";

import { useState } from "react";
import Link from "next/link";

import { ErrorState } from "@/components/common/states";
import { Button } from "@/components/ui/button";
import { isApiError } from "@/lib/api";
import { useReport } from "@/lib/hooks";
import { routes } from "@/lib/routes";
import type { ReportDetail } from "@/lib/types";

import { DetectionSection } from "./detection-section";
import { EvidenceExplainerCard } from "./evidence-explainer-card";
import { EvidenceSection } from "./evidence-section";
import { ExternalSharingCard } from "./external-sharing-card";
import { FactHistorySection } from "./fact-history-section";
import { FeedbackCard } from "./feedback-card";
import { InvestigationSection } from "./investigation-section";
import { RelatedSection } from "./related-section";
import { ReportHeader } from "./report-header";
import { ReportSkeleton } from "./report-skeleton";
import { ShareDialog } from "./share-dialog";
import { useMarkRead } from "./use-mark-read";
import { WhatChanged } from "./what-changed";
import { WhyItMatters } from "./why-it-matters";

/**
 * The intelligence card: what changed (facts), why it matters to you (agent assessment),
 * the evidence and how sure we are, how it was detected and investigated — plus feedback
 * and human-approved sharing.
 */
export function ReportScreen({ wid, rid }: { wid: string; rid: string }) {
  const { data: report, error, mutate } = useReport(wid, rid);
  useMarkRead(wid, report);

  if (error && !report) {
    const notFound = isApiError(error) && error.status === 404;
    return (
      <div className="space-y-4">
        <ErrorState
          error={error}
          title={notFound ? "This intelligence card doesn't exist" : undefined}
          onRetry={() => void mutate()}
        />
        {notFound ? (
          <div className="flex justify-center">
            <Button asChild variant="outline" size="sm">
              <Link href={routes.intel(wid)}>Back to intelligence</Link>
            </Button>
          </div>
        ) : null}
      </div>
    );
  }
  if (!report) return <ReportSkeleton />;

  // Keyed by id so per-card state (feedback form, "new" marker) resets when navigating between cards.
  return <ReportView key={report.id} wid={wid} report={report} />;
}

function ReportView({ wid, report }: { wid: string; report: ReportDetail }) {
  // Captured once, when the card first renders: opening it marks it read right away.
  const [wasUnread] = useState(report.unread);
  const [shareOpen, setShareOpen] = useState(false);

  return (
    <article className="space-y-8">
      <ReportHeader wid={wid} report={report} wasUnread={wasUnread} onShare={() => setShareOpen(true)} />

      <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_20rem] xl:grid-cols-[minmax(0,1fr)_22rem]">
        <div className="min-w-0 space-y-10">
          <WhatChanged report={report} />
          <WhyItMatters wid={wid} report={report} />
          <EvidenceSection report={report} />
          <FactHistorySection wid={wid} report={report} />
          <DetectionSection report={report} />
          <InvestigationSection wid={wid} report={report} />
        </div>
        <aside className="min-w-0 space-y-4" aria-label="Feedback and sharing">
          <FeedbackCard wid={wid} report={report} />
          <EvidenceExplainerCard status={report.evidence_status} />
          <ExternalSharingCard wid={wid} approvals={report.approvals} onShare={() => setShareOpen(true)} />
        </aside>
      </div>

      <RelatedSection wid={wid} reports={report.related} />

      <ShareDialog wid={wid} report={report} open={shareOpen} onOpenChange={setShareOpen} />
    </article>
  );
}
