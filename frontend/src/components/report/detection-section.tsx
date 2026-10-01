import { MetaBadge } from "@/components/common/badges";
import { ExternalLink } from "@/components/common/links";
import { DefinitionList, Section } from "@/components/common/page-header";
import { DETECTION_SOURCE, EVENT_STATUS, MATERIALITY } from "@/lib/labels";
import type { ReportDetail } from "@/lib/types";

import { DiffView } from "./diff-view";

/** How the change was noticed and why it cleared the materiality gate. */
export function DetectionSection({ report }: { report: ReportDetail }) {
  const { event } = report;
  const items = [
    { label: "Detected by", value: <MetaBadge meta={DETECTION_SOURCE[event.detection_source]} tooltip={false} /> },
    {
      label: "Materiality",
      value: (
        <div className="space-y-1">
          <MetaBadge meta={MATERIALITY[event.materiality]} tooltip={false} />
          {event.materiality_reason ? (
            <p className="text-sm text-pretty text-muted-foreground">{event.materiality_reason}</p>
          ) : null}
        </div>
      ),
    },
    { label: "Event status", value: <MetaBadge meta={EVENT_STATUS[event.status]} tooltip={false} /> },
  ];
  if (event.source_url) {
    items.push({
      label: "Source",
      value: <ExternalLink href={event.source_url} className="max-w-full text-sm" />,
    });
  }

  return (
    <Section
      id="detection"
      title="Detection"
      description="How SignalLens noticed this change, and why it was judged material enough to investigate."
    >
      <div className="space-y-4 rounded-xl border bg-card p-4">
        <DefinitionList items={items} className="gap-y-3" />
        {event.diff_excerpt ? <DiffView diff={event.diff_excerpt} /> : null}
      </div>
    </Section>
  );
}
