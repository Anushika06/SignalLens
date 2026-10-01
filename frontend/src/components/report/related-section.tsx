import { Section } from "@/components/common/page-header";
import { ReportRow } from "@/components/intel/report-row";
import type { ReportSummary } from "@/lib/types";

/** Other cards about the same entity and area (the API returns up to five). */
export function RelatedSection({ wid, reports }: { wid: string; reports: ReportSummary[] }) {
  if (reports.length === 0) return null;
  return (
    <Section id="related" title="Related intelligence" description="Other cards about the same company and area.">
      <ul className="divide-y overflow-hidden rounded-xl border bg-card">
        {reports.map((report) => (
          <li key={report.id}>
            <ReportRow wid={wid} report={report} />
          </li>
        ))}
      </ul>
    </Section>
  );
}
