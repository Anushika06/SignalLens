import { ArrowRight } from "lucide-react";

import { Chip, MetaBadge, WithTooltip } from "@/components/common/badges";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { IMPORTANCE, IMPORTANCE_ORDER, MATERIALITY } from "@/lib/labels";
import type { PlanArea, PolicyArea, PolicyView } from "@/lib/types";

/** Plan importance vs the importance in effect now (a learned rule may have changed it). */
function ImportanceCell({ area }: { area: PolicyArea }) {
  if (area.importance === area.effective_importance) {
    return <MetaBadge meta={IMPORTANCE[area.importance]} />;
  }
  const planned = IMPORTANCE[area.importance];
  const effective = IMPORTANCE[area.effective_importance];
  return (
    <div className="space-y-1">
      <WithTooltip
        focusable
        content={`Set to ${planned.label} in your plan; now ${effective.label} because of a learned rule from your feedback. You can undo it under Learned rules.`}
      >
        <span className="inline-flex items-center gap-1.5 rounded-md">
          <MetaBadge meta={planned} tooltip={false} className="opacity-60" />
          <ArrowRight className="size-3 text-muted-foreground" aria-hidden="true" />
          <span className="sr-only">now</span>
          <MetaBadge meta={effective} tooltip={false} />
        </span>
      </WithTooltip>
      <p className="text-xs text-muted-foreground">Adjusted by a learned rule</p>
    </div>
  );
}

function ThresholdCell({ area }: { area: PolicyArea }) {
  const meta = MATERIALITY[area.threshold];
  if (area.threshold === "none") {
    return <span className="text-sm text-muted-foreground">Any change</span>;
  }
  return (
    <span className="inline-flex items-center gap-1.5 text-xs text-muted-foreground">
      <MetaBadge
        meta={meta}
        tooltip={`Changes rated ${meta.label.toLowerCase()} materiality or higher are investigated. Anything below is filtered and logged.`}
      />
      and above
    </span>
  );
}

function RoutingCell({ area }: { area: PolicyArea }) {
  if (area.route_to.length === 0) return <span className="text-sm text-muted-foreground">No team</span>;
  return (
    <div className="flex flex-wrap gap-1">
      {area.route_to.map((team) => (
        <Chip key={team}>{team}</Chip>
      ))}
    </div>
  );
}

function byEffectiveImportance(a: PolicyArea, b: PolicyArea) {
  return IMPORTANCE_ORDER.indexOf(a.effective_importance) - IMPORTANCE_ORDER.indexOf(b.effective_importance);
}

/** Areas of the active policy: how much each matters, the bar a change must clear, who hears. */
export function AreasTable({ policy }: { policy: PolicyView }) {
  const specByKey = new Map<string, PlanArea>(policy.spec.areas.map((area) => [area.key, area]));
  const areas = [...policy.areas].sort(byEffectiveImportance);

  if (areas.length === 0) {
    return <p className="rounded-xl border border-dashed p-4 text-sm text-muted-foreground">This plan has no areas.</p>;
  }

  return (
    <div className="space-y-4">
      <p className="max-w-3xl text-sm text-pretty text-muted-foreground">
        Importance decides delivery: critical and high intelligence reaches the owning teams immediately; medium and low
        go to the daily digest. The alert threshold is the minimum materiality a change needs before SignalLens
        investigates it.
      </p>

      <div className="hidden overflow-hidden rounded-xl border bg-card md:block">
        <Table>
          <TableHeader className="bg-muted/40">
            <TableRow className="hover:bg-transparent">
              <TableHead className="pl-4">Area</TableHead>
              <TableHead>Importance</TableHead>
              <TableHead>Alert threshold</TableHead>
              <TableHead className="pr-4">Routed to</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {areas.map((area) => {
              const spec = specByKey.get(area.key);
              return (
                <TableRow key={area.key}>
                  <TableCell className="max-w-md py-3 pl-4 whitespace-normal">
                    <p className="font-medium">{area.label}</p>
                    {spec?.description ? (
                      <p className="line-clamp-2 text-xs text-pretty text-muted-foreground">{spec.description}</p>
                    ) : null}
                  </TableCell>
                  <TableCell className="align-top pt-3">
                    <ImportanceCell area={area} />
                  </TableCell>
                  <TableCell className="align-top pt-3">
                    <ThresholdCell area={area} />
                  </TableCell>
                  <TableCell className="pr-4 align-top whitespace-normal pt-3">
                    <RoutingCell area={area} />
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </div>

      <ul className="divide-y rounded-xl border bg-card md:hidden">
        {areas.map((area) => {
          const spec = specByKey.get(area.key);
          return (
            <li key={area.key} className="space-y-3 p-4">
              <div>
                <p className="text-sm font-medium">{area.label}</p>
                {spec?.description ? <p className="text-xs text-pretty text-muted-foreground">{spec.description}</p> : null}
              </div>
              <dl className="grid grid-cols-2 gap-3 text-sm">
                <div className="space-y-1">
                  <dt className="text-xs text-muted-foreground">Importance</dt>
                  <dd>
                    <ImportanceCell area={area} />
                  </dd>
                </div>
                <div className="space-y-1">
                  <dt className="text-xs text-muted-foreground">Alert threshold</dt>
                  <dd>
                    <ThresholdCell area={area} />
                  </dd>
                </div>
                <div className="col-span-2 space-y-1">
                  <dt className="text-xs text-muted-foreground">Routed to</dt>
                  <dd>
                    <RoutingCell area={area} />
                  </dd>
                </div>
              </dl>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
