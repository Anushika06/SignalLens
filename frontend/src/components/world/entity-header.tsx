import Link from "next/link";
import { ArrowLeft, Lightbulb } from "lucide-react";

import { Chip, MetaBadge } from "@/components/common/badges";
import { ExternalLink } from "@/components/common/links";
import { PageHeader } from "@/components/common/page-header";
import { RelativeTime } from "@/components/common/relative-time";
import { Stat, StatGrid } from "@/components/common/stat";
import { Button } from "@/components/ui/button";
import { formatNumber } from "@/lib/format";
import { ENTITY_KIND, ENTITY_ROLE } from "@/lib/labels";
import { routes } from "@/lib/routes";
import type { EntitySummary } from "@/lib/types";

export function BackToWorld({ wid }: { wid: string }) {
  return (
    <Link
      href={routes.world(wid)}
      className="inline-flex items-center gap-1 text-sm text-muted-foreground transition-colors hover:text-foreground"
    >
      <ArrowLeft className="size-3.5" aria-hidden="true" />
      World state
    </Link>
  );
}

/** Who this entity is: role, names it goes by, official domains and headline numbers. */
export function EntityHeader({ wid, entity }: { wid: string; entity: EntitySummary }) {
  return (
    <div className="space-y-5">
      <BackToWorld wid={wid} />
      <PageHeader
        eyebrow={
          <>
            <MetaBadge meta={ENTITY_ROLE[entity.role]} />
            <MetaBadge meta={ENTITY_KIND[entity.kind]} tooltip={false} />
          </>
        }
        title={entity.name}
        description={entity.description || undefined}
        actions={
          <Button asChild variant="outline" size="sm">
            <Link href={routes.intel(wid, { entity: entity.id, view: "all" })}>
              <Lightbulb aria-hidden="true" />
              View intelligence
            </Link>
          </Button>
        }
      />

      <div className="grid gap-5 rounded-xl border bg-card p-4 md:grid-cols-[minmax(0,1fr)_auto] md:gap-8">
        <dl className="grid gap-3 text-sm sm:grid-cols-[max-content_minmax(0,1fr)] sm:gap-x-6">
          <dt className="text-muted-foreground">Also known as</dt>
          <dd className="flex min-w-0 flex-wrap gap-1.5">
            {entity.aliases.length > 0 ? (
              entity.aliases.map((alias) => <Chip key={alias}>{alias}</Chip>)
            ) : (
              <span className="text-muted-foreground">No aliases recorded</span>
            )}
          </dd>
          <dt className="text-muted-foreground">Official domains</dt>
          <dd className="flex min-w-0 flex-wrap gap-x-3 gap-y-1">
            {entity.official_domains.length > 0 ? (
              entity.official_domains.map((domain) => (
                <ExternalLink key={domain} href={`https://${domain}`} className="font-mono text-xs">
                  {domain}
                </ExternalLink>
              ))
            ) : (
              <span className="text-muted-foreground">None recorded</span>
            )}
          </dd>
        </dl>
        <StatGrid className="grid-cols-3 gap-6 border-t pt-4 md:border-t-0 md:border-l md:pt-0 md:pl-8">
          <Stat label="Tracked facts" value={formatNumber(entity.facts_count)} />
          <Stat label="Reports" value={formatNumber(entity.reports_count)} />
          <Stat
            label="Last change"
            valueClassName="text-sm font-medium"
            value={entity.last_change_at ? <RelativeTime value={entity.last_change_at} /> : "None yet"}
          />
        </StatGrid>
      </div>
    </div>
  );
}
