import Link from "next/link";
import { Archive, ArrowRight, ThumbsDown, ThumbsUp } from "lucide-react";

import { cn } from "@/lib/utils";
import { AreaChip, EvidenceBadge, SeverityDot, ToneBadge, WithTooltip } from "@/components/common/badges";
import { RelativeTime } from "@/components/common/relative-time";
import { FEEDBACK_REASON, FEEDBACK_VERDICT } from "@/lib/labels";
import { routes } from "@/lib/routes";
import type { ReportSummary } from "@/lib/types";

/** Compact "before → after" for value changes, e.g. "2% flat → 0% for 90 days". */
export function StateChange({ report, className }: { report: Pick<ReportSummary, "previous_state" | "current_state">; className?: string }) {
  if (!report.previous_state && !report.current_state) return null;
  return (
    <span className={cn("inline-flex min-w-0 items-center gap-1", className)}>
      {report.previous_state ? <span className="truncate line-through decoration-muted-foreground/50">{report.previous_state}</span> : null}
      {report.previous_state && report.current_state ? <ArrowRight className="size-3 shrink-0" aria-label="changed to" /> : null}
      {report.current_state ? <span className="truncate font-medium text-foreground">{report.current_state}</span> : null}
    </span>
  );
}

/** How the user rated this report, if they did. */
export function FeedbackMark({ feedback }: { feedback: ReportSummary["feedback"] }) {
  if (!feedback) return null;
  const Icon = feedback.verdict === "relevant" ? ThumbsUp : ThumbsDown;
  return (
    <WithTooltip content={`You marked this ${FEEDBACK_VERDICT[feedback.verdict].toLowerCase()}: ${FEEDBACK_REASON[feedback.reason]}`}>
      <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
        <Icon className="size-3" aria-hidden="true" />
        <span className="sr-only">{FEEDBACK_VERDICT[feedback.verdict]}: </span>
        {FEEDBACK_REASON[feedback.reason]}
      </span>
    </WithTooltip>
  );
}

type ReportRowProps = {
  wid: string;
  report: ReportSummary;
  /** Hide the entity name (e.g. on that entity's own page). */
  showEntity?: boolean;
  className?: string;
};

/**
 * One intelligence card in a list: severity dot, title, change label, area, entity, evidence,
 * relative time, unread marker and feedback state. The whole row is clickable (stretched link).
 */
export function ReportRow({ wid, report, showEntity = true, className }: ReportRowProps) {
  // Backfilled history was *detected* at baseline; when it happened is the useful time.
  const shownTime = report.is_historical ? (report.occurred_at ?? report.detected_at) : report.detected_at;
  return (
    <div
      className={cn(
        "group relative flex gap-3 px-4 py-3 transition-colors hover:bg-muted/50 has-[a:focus-visible]:bg-muted/50 has-[a:focus-visible]:ring-2 has-[a:focus-visible]:ring-ring has-[a:focus-visible]:ring-inset",
        className,
      )}
    >
      <div className="flex w-2 shrink-0 flex-col items-center gap-1.5 pt-1.5">
        <SeverityDot severity={report.severity} />
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-start gap-3">
          <Link
            href={routes.report(wid, report.id)}
            className={cn(
              "min-w-0 flex-1 text-sm leading-snug text-pretty after:absolute after:inset-0 focus-visible:outline-none",
              report.unread ? "font-semibold" : "font-medium",
            )}
          >
            {report.unread ? (
              <span className="mr-1.5 inline-block size-1.5 -translate-y-0.5 rounded-full bg-brand" aria-hidden="true" />
            ) : null}
            {report.unread ? <span className="sr-only">Unread: </span> : null}
            {report.title}
          </Link>
          <div className="relative z-10 hidden shrink-0 items-center gap-3 sm:flex">
            <EvidenceBadge status={report.evidence_status} />
            <RelativeTime value={shownTime} className="w-24 text-right text-xs text-muted-foreground" />
          </div>
        </div>
        <div className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1.5 text-xs text-muted-foreground">
          <span className="font-medium text-foreground/80">{report.change_label}</span>
          <AreaChip label={report.area_label} />
          {showEntity && report.entity ? <span>{report.entity.name}</span> : null}
          <StateChange report={report} className="max-w-full sm:max-w-md" />
          {report.is_historical ? (
            <ToneBadge tone="gray" icon={Archive}>
              Historical
            </ToneBadge>
          ) : null}
          <span className="relative z-10">
            <FeedbackMark feedback={report.feedback} />
          </span>
          <span className="relative z-10 flex items-center gap-2 sm:hidden">
            <EvidenceBadge status={report.evidence_status} />
            <RelativeTime value={shownTime} />
          </span>
        </div>
      </div>
    </div>
  );
}
