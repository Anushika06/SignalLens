import Link from "next/link";

import { cn } from "@/lib/utils";
import { Chip, MetaBadge } from "@/components/common/badges";
import { RelativeTime } from "@/components/common/relative-time";
import { formatNumber } from "@/lib/format";
import { ENTITY_KIND, ENTITY_ROLE } from "@/lib/labels";
import { routes } from "@/lib/routes";
import type { OverviewArea, SubjectCard } from "@/lib/types";

const MAX_AREAS = 4;

/**
 * The companies (or products, regulators…) this workspace was set up to monitor. A card lays
 * its content out in a row when it is wide enough (container query), so a single subject
 * doesn't leave the row half empty.
 */
export function SubjectCards({ wid, subjects, areas }: { wid: string; subjects: SubjectCard[]; areas: OverviewArea[] }) {
  const areaLabel = new Map(areas.map((area) => [area.key, area.label]));
  return (
    <ul className={cn("grid gap-3", subjects.length > 1 && "sm:grid-cols-2")}>
      {subjects.map((subject) => {
        const shown = subject.areas.slice(0, MAX_AREAS);
        const more = subject.areas.length - shown.length;
        return (
          <li
            key={subject.entity_id}
            className="group @container relative rounded-xl border bg-card p-4 transition-colors hover:border-foreground/20 has-[a:focus-visible]:ring-2 has-[a:focus-visible]:ring-ring"
          >
            <div className="flex flex-col gap-3 @xl:flex-row @xl:items-center @xl:gap-6">
              <div className="flex min-w-0 items-start justify-between gap-3 @xl:w-56 @xl:shrink-0 @xl:flex-col @xl:justify-start @xl:gap-1.5">
                <div className="min-w-0">
                  <Link
                    href={routes.entity(wid, subject.entity_id)}
                    className="block truncate font-semibold tracking-tight after:absolute after:inset-0 focus-visible:outline-none"
                  >
                    {subject.name}
                  </Link>
                  <p className="mt-0.5 text-xs text-muted-foreground">
                    {ENTITY_KIND[subject.kind].label} · last change{" "}
                    <RelativeTime value={subject.last_change_at} className="relative z-10" />
                  </p>
                </div>
                <MetaBadge meta={ENTITY_ROLE[subject.role]} tooltip={false} />
              </div>
              <dl className="grid grid-cols-2 gap-3 @xl:w-56 @xl:shrink-0">
                <div>
                  <dt className="text-xs text-muted-foreground">Facts tracked</dt>
                  <dd className="metric text-lg font-semibold">{formatNumber(subject.facts_count)}</dd>
                </div>
                <div>
                  <dt className="text-xs text-muted-foreground">Reports · 30 days</dt>
                  <dd className="metric text-lg font-semibold">{formatNumber(subject.reports_30d)}</dd>
                </div>
              </dl>
              {shown.length > 0 ? (
                <div className="flex flex-wrap gap-1 @xl:flex-1">
                  {shown.map((key) => (
                    <Chip key={key}>{areaLabel.get(key) ?? key}</Chip>
                  ))}
                  {more > 0 ? <Chip>+{more} more</Chip> : null}
                </div>
              ) : null}
            </div>
          </li>
        );
      })}
    </ul>
  );
}
