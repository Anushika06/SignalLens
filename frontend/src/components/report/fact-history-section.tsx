import Link from "next/link";
import { ArrowRight } from "lucide-react";

import { Section } from "@/components/common/page-header";
import { Button } from "@/components/ui/button";
import { FactHistory } from "@/components/world/fact-history";
import { routes } from "@/lib/routes";
import type { ReportDetail } from "@/lib/types";

/** The tracked value this card changed, with every version SignalLens has recorded. */
export function FactHistorySection({ wid, report }: { wid: string; report: ReportDetail }) {
  const fact = report.fact;
  if (!fact) return null;
  return (
    <Section
      id="fact-history"
      title="Fact history"
      description={
        <>
          How <span className="font-medium text-foreground">{fact.label}</span> has changed. Effective is when a value
          took effect; Observed is when SignalLens saw it.
        </>
      }
      actions={
        report.entity ? (
          <Button asChild variant="ghost" size="sm">
            <Link href={routes.entity(wid, report.entity.id)}>
              World state
              <ArrowRight aria-hidden="true" />
            </Link>
          </Button>
        ) : null
      }
    >
      <div className="rounded-xl border bg-card p-4">
        <p className="mb-4 font-mono text-xs break-all text-muted-foreground">{fact.key}</p>
        <FactHistory versions={fact.history} />
      </div>
    </Section>
  );
}
