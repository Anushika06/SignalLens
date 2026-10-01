import Link from "next/link";
import { ChevronRight } from "lucide-react";

import { MetaBadge } from "@/components/common/badges";
import { RelativeTime } from "@/components/common/relative-time";
import { formatNumber } from "@/lib/format";
import { ENTITY_KIND, ENTITY_ROLE } from "@/lib/labels";
import { routes } from "@/lib/routes";
import type { EntitySummary } from "@/lib/types";

/** One entity in the world-state grid; the whole card opens the entity page. */
export function EntityCard({ wid, entity }: { wid: string; entity: EntitySummary }) {
  return (
    <Link
      href={routes.entity(wid, entity.id)}
      className="group flex h-full flex-col rounded-xl border bg-card p-4 transition-colors outline-none hover:border-foreground/20 hover:bg-muted/30 focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 space-y-1.5">
          <h3 className="truncate text-sm font-semibold tracking-tight">{entity.name}</h3>
          <div className="flex flex-wrap items-center gap-1.5">
            <MetaBadge meta={ENTITY_ROLE[entity.role]} tooltip={false} />
            <MetaBadge meta={ENTITY_KIND[entity.kind]} tooltip={false} />
          </div>
        </div>
        <ChevronRight
          className="mt-0.5 size-4 shrink-0 text-muted-foreground transition-transform group-hover:translate-x-0.5"
          aria-hidden="true"
        />
      </div>

      <div className="flex-1">
        {entity.description ? (
          <p className="mt-3 line-clamp-2 text-sm text-pretty text-muted-foreground">{entity.description}</p>
        ) : null}
        {entity.official_domains.length > 0 ? (
          <p className="mt-2 truncate font-mono text-xs text-muted-foreground">
            {entity.official_domains.join(" · ")}
          </p>
        ) : null}
      </div>

      <dl className="mt-4 grid grid-cols-3 gap-2 border-t pt-3">
        <div className="min-w-0">
          <dt className="text-xs text-muted-foreground">Facts</dt>
          <dd className="metric text-sm font-semibold">{formatNumber(entity.facts_count)}</dd>
        </div>
        <div className="min-w-0">
          <dt className="text-xs text-muted-foreground">Reports</dt>
          <dd className="metric text-sm font-semibold">{formatNumber(entity.reports_count)}</dd>
        </div>
        <div className="min-w-0">
          <dt className="text-xs text-muted-foreground">Last change</dt>
          <dd className="truncate text-sm">
            {entity.last_change_at ? <RelativeTime value={entity.last_change_at} /> : <span className="text-muted-foreground">None yet</span>}
          </dd>
        </div>
      </dl>
    </Link>
  );
}
