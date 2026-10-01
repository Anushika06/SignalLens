import { Chip } from "@/components/common/badges";
import { Section } from "@/components/common/page-header";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { IMPORTANCE, IMPORTANCE_ORDER } from "@/lib/labels";
import type { Importance, MonitoringPlan, PlanArea } from "@/lib/types";

import { ControlLabel, ReviewItem, WhyLine } from "./review-item";

type AreasSectionProps = {
  spec: MonitoringPlan;
  onChange: (key: string, patch: Partial<PlanArea>) => void;
};

function AreaItem({ area, onChange }: { area: PlanArea; onChange: AreasSectionProps["onChange"] }) {
  const selectId = `area-${area.key}-importance`;
  return (
    <ReviewItem
      title={area.label}
      badges={<code className="rounded bg-muted px-1 font-mono text-[11px] text-muted-foreground">{area.key}</code>}
      enabled={area.enabled}
      onEnabledChange={(enabled) => onChange(area.key, { enabled })}
      switchLabel={`Monitor ${area.label}`}
      controls={
        <div className="space-y-1.5">
          <ControlLabel htmlFor={selectId}>Importance</ControlLabel>
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <Select value={area.importance} onValueChange={(value) => onChange(area.key, { importance: value as Importance })}>
              <SelectTrigger id={selectId} size="sm" className="w-32">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {IMPORTANCE_ORDER.map((level) => (
                  <SelectItem key={level} value={level}>
                    {IMPORTANCE[level].label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <span className="text-xs text-muted-foreground">{IMPORTANCE[area.importance].description}</span>
          </div>
        </div>
      }
    >
      {area.description ? <p className="text-sm text-pretty">{area.description}</p> : null}
      <p className="flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
        <span>Routes to</span>
        {area.route_to.length > 0 ? (
          area.route_to.map((team) => (
            <Chip key={team} className="text-foreground">
              {team}
            </Chip>
          ))
        ) : (
          <span className="text-foreground/80">no team yet (you can assign one in Settings)</span>
        )}
      </p>
      <WhyLine reason={area.reason} />
    </ReviewItem>
  );
}

/** The kinds of change the plan cares about, how urgent each is, and who hears about it. */
export function AreasSection({ spec, onChange }: AreasSectionProps) {
  return (
    <Section
      id="areas"
      title={`Areas · ${spec.areas.length}`}
      description="Critical and high areas alert their teams immediately; medium and low go to the daily digest. Turning an area off skips the values and sources that only cover it."
    >
      {spec.areas.length === 0 ? (
        <p className="text-sm text-muted-foreground">The planner didn&apos;t propose any areas.</p>
      ) : (
        <ul className="space-y-2">
          {spec.areas.map((area) => (
            <AreaItem key={area.key} area={area} onChange={onChange} />
          ))}
        </ul>
      )}
    </Section>
  );
}
