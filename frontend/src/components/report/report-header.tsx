import Link from "next/link";
import { Archive, ArrowLeft, Share2 } from "lucide-react";

import { AreaChip, EvidenceBadge, SeverityBadge, ToneBadge, WithTooltip } from "@/components/common/badges";
import { EntityLink } from "@/components/common/links";
import { RelativeTime } from "@/components/common/relative-time";
import { FeedbackMark } from "@/components/intel/report-row";
import { Button } from "@/components/ui/button";
import { formatDate, formatDateTime } from "@/lib/format";
import { routes } from "@/lib/routes";
import type { ReportDetail } from "@/lib/types";

type ReportHeaderProps = {
  wid: string;
  report: ReportDetail;
  /** The card was unread when it was opened. */
  wasUnread: boolean;
  onShare: () => void;
};

/**
 * Title block of an intelligence card. Severity (how much it matters to you) and evidence
 * status (how sure we are) sit side by side but are deliberately separate badges.
 */
export function ReportHeader({ wid, report, wasUnread, onShare }: ReportHeaderProps) {
  return (
    <header className="space-y-4">
      <Link
        href={routes.intel(wid)}
        className="inline-flex items-center gap-1.5 text-sm text-muted-foreground transition-colors hover:text-foreground"
      >
        <ArrowLeft className="size-4" aria-hidden="true" />
        Intelligence
      </Link>

      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0 space-y-3">
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1.5 text-sm">
            <span className="font-medium text-brand">{report.change_label}</span>
            <span aria-hidden="true" className="text-muted-foreground">
              ·
            </span>
            <AreaChip label={report.area_label} />
            {report.entity ? (
              <>
                <span aria-hidden="true" className="text-muted-foreground">
                  ·
                </span>
                <EntityLink wid={wid} entity={report.entity} />
              </>
            ) : null}
          </div>

          <h1 className="text-xl font-semibold tracking-tight text-balance sm:text-2xl">{report.title}</h1>

          <div className="flex flex-wrap items-center gap-2">
            <SeverityBadge severity={report.severity} focusable />
            <EvidenceBadge status={report.evidence_status} explain="all" focusable />
            {report.is_historical ? (
              <WithTooltip content="Reconstructed from web-archive captures when monitoring started. Historical changes are never sent as alerts.">
                <ToneBadge tone="gray" icon={Archive}>
                  Historical (from web archive)
                </ToneBadge>
              </WithTooltip>
            ) : null}
            {wasUnread ? <ToneBadge tone="brand">New</ToneBadge> : null}
          </div>

          <dl className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
            <div className="flex items-center gap-1">
              <dt>Detected</dt>
              <dd className="text-foreground/80">
                <RelativeTime value={report.detected_at} />
                <span className="hidden sm:inline"> · {formatDateTime(report.detected_at)}</span>
              </dd>
            </div>
            {report.occurred_at ? (
              <div className="flex items-center gap-1">
                <WithTooltip content="When the change took effect, if the sources say so. Detected is when SignalLens noticed it.">
                  <dt className="underline decoration-dotted underline-offset-2">Occurred</dt>
                </WithTooltip>
                <dd className="text-foreground/80">
                  <time dateTime={report.occurred_at}>{formatDate(report.occurred_at)}</time>
                </dd>
              </div>
            ) : null}
            {report.feedback ? (
              <div className="flex items-center gap-1">
                <dt className="sr-only">Your feedback</dt>
                <dd>
                  <FeedbackMark feedback={report.feedback} />
                </dd>
              </div>
            ) : null}
          </dl>
        </div>

        <div className="flex shrink-0">
          <Button variant="outline" onClick={onShare}>
            <Share2 aria-hidden="true" />
            Share externally…
          </Button>
        </div>
      </div>
    </header>
  );
}
