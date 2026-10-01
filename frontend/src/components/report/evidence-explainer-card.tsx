import { cn } from "@/lib/utils";
import { EvidenceBadge } from "@/components/common/badges";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { EVIDENCE, EVIDENCE_ORDER } from "@/lib/labels";
import type { EvidenceStatus } from "@/lib/types";

/**
 * "How sure are we?" — the five evidence statuses and the rule behind each, with this card's
 * status highlighted. Statuses are computed by code from the evidence, never asserted by a model.
 */
export function EvidenceExplainerCard({ status }: { status: EvidenceStatus }) {
  return (
    <Card size="sm">
      <CardHeader>
        <CardTitle>How sure are we?</CardTitle>
        <CardDescription>
          Evidence status follows fixed rules. Quotes are checked against pages the agent actually fetched.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <ul className="space-y-1.5">
          {EVIDENCE_ORDER.map((key) => {
            const current = key === status;
            return (
              <li
                key={key}
                aria-current={current ? "true" : undefined}
                className={cn(
                  "rounded-lg border p-2.5",
                  current ? "border-brand/30 bg-brand/5" : "border-transparent",
                )}
              >
                <div className="flex flex-wrap items-center gap-2">
                  <EvidenceBadge status={key} explain={false} />
                  {current ? <span className="text-xs font-medium text-brand">This card</span> : null}
                </div>
                <p className={cn("mt-1 text-xs text-pretty", current ? "text-foreground/80" : "text-muted-foreground")}>
                  {EVIDENCE[key].description}
                </p>
              </li>
            );
          })}
        </ul>
        <p className="border-t pt-3 text-xs text-pretty text-muted-foreground">
          Severity is a separate question — how much this matters to you, not how sure we are. Unverified items are
          never more than Medium, and single-source items are never Critical.
        </p>
      </CardContent>
    </Card>
  );
}
