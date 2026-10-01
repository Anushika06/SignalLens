import { ArrowDownLeft, ArrowUpRight } from "lucide-react";

import { MetaBadge } from "@/components/common/badges";
import { EntityLink } from "@/components/common/links";
import { Section } from "@/components/common/page-header";
import { RelativeTime } from "@/components/common/relative-time";
import { formatDate, humanize } from "@/lib/format";
import { ENTITY_KIND } from "@/lib/labels";
import type { EntityRelationship, EntitySummary } from "@/lib/types";

/** Reads as a sentence: "Razorpay competes with Cashfree" / "Reserve Bank of India regulates Razorpay". */
function RelationshipSentence({ wid, entity, relationship }: { wid: string; entity: EntitySummary; relationship: EntityRelationship }) {
  const predicate = humanize(relationship.predicate).toLowerCase();
  const self = <span className="font-medium">{entity.name}</span>;
  const other = <EntityLink wid={wid} entity={relationship.other} className="text-brand" />;
  return relationship.direction === "out" ? (
    <>
      {self} {predicate} {other}
    </>
  ) : (
    <>
      {other} {predicate} {self}
    </>
  );
}

type EntityRelationshipsProps = {
  wid: string;
  entity: EntitySummary;
  relationships: EntityRelationship[];
};

export function EntityRelationships({ wid, entity, relationships }: EntityRelationshipsProps) {
  return (
    <Section
      id="relationships"
      title="Relationships"
      description="How this entity connects to others in your world state."
    >
      {relationships.length === 0 ? (
        <p className="rounded-xl border border-dashed p-4 text-sm text-pretty text-muted-foreground">
          No relationships recorded yet. They are added as SignalLens sees competitors, partners, products and
          regulators connected to this entity in its sources.
        </p>
      ) : (
        <ul className="divide-y rounded-xl border bg-card">
          {relationships.map((relationship) => {
            const Icon = relationship.direction === "out" ? ArrowUpRight : ArrowDownLeft;
            return (
              <li key={relationship.id} className="flex gap-3 px-4 py-3">
                <span className="mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-md bg-muted text-muted-foreground">
                  <Icon className="size-3.5" aria-hidden="true" />
                  <span className="sr-only">{relationship.direction === "out" ? "Outgoing" : "Incoming"} relationship:</span>
                </span>
                <div className="min-w-0 flex-1 space-y-1">
                  <p className="text-sm text-pretty">
                    <RelationshipSentence wid={wid} entity={entity} relationship={relationship} />
                  </p>
                  <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
                    <MetaBadge meta={ENTITY_KIND[relationship.other.kind]} tooltip={false} />
                    <span>First seen {formatDate(relationship.first_seen_at)}</span>
                    <span aria-hidden="true">·</span>
                    <span>
                      Last seen <RelativeTime value={relationship.last_seen_at} />
                    </span>
                  </div>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </Section>
  );
}
