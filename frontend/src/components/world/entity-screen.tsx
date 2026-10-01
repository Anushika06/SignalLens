"use client";

import { PageSkeleton } from "@/components/common/skeletons";
import { ErrorState } from "@/components/common/states";
import { useEntity } from "@/lib/hooks";

import { EntityFacts } from "./entity-facts";
import { BackToWorld, EntityHeader } from "./entity-header";
import { EntityRelationships } from "./entity-relationships";
import { EntityTimeline } from "./entity-timeline";

/** One entity's slice of the world state: who it is, its tracked facts, links and history. */
export function EntityScreen({ wid, eid }: { wid: string; eid: string }) {
  const { data, error, isLoading, mutate } = useEntity(wid, eid);

  if (error) {
    return (
      <div className="space-y-6">
        <BackToWorld wid={wid} />
        <ErrorState error={error} onRetry={() => void mutate()} />
      </div>
    );
  }
  if (isLoading || !data) return <PageSkeleton />;

  return (
    <div className="space-y-10">
      <EntityHeader wid={wid} entity={data.entity} />
      <EntityFacts wid={wid} entity={data.entity} facts={data.facts} />
      <div className="grid gap-10 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <EntityTimeline wid={wid} items={data.timeline} />
        <EntityRelationships wid={wid} entity={data.entity} relationships={data.relationships} />
      </div>
    </div>
  );
}
