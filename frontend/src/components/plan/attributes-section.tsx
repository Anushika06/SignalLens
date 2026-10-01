import { AreaChip, Chip } from "@/components/common/badges";
import { Section } from "@/components/common/page-header";
import type { MonitoringPlan, PlanAttribute } from "@/lib/types";

import { attributeSkipReason, indexSpec, type SpecIndex, VALUE_TYPE_LABEL } from "./plan-spec";
import { ReviewItem } from "./review-item";

type AttributesSectionProps = {
  spec: MonitoringPlan;
  onChange: (index: number, patch: Partial<PlanAttribute>) => void;
};

function AttributeItem({
  attribute,
  position,
  index,
  onChange,
}: {
  attribute: PlanAttribute;
  position: number;
  index: SpecIndex;
  onChange: AttributesSectionProps["onChange"];
}) {
  const entityName = index.entityName(attribute.entity_ref);
  return (
    <ReviewItem
      title={attribute.label}
      badges={
        <>
          <Chip>{VALUE_TYPE_LABEL[attribute.value_type]}</Chip>
          <Chip className="text-foreground">{entityName}</Chip>
          <AreaChip label={index.areaLabel(attribute.area)} />
        </>
      }
      enabled={attribute.enabled}
      onEnabledChange={(enabled) => onChange(position, { enabled })}
      switchLabel={`Track ${attribute.label} for ${entityName}`}
      skippedBecause={attributeSkipReason(attribute, index)}
    >
      {attribute.hint ? <p className="text-sm text-pretty">{attribute.hint}</p> : null}
      <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
        <code className="rounded bg-muted px-1 font-mono text-[11px]">{attribute.key}</code>
        {attribute.source_refs.length > 0 ? (
          <span className="min-w-0 break-words">Read from {attribute.source_refs.map(index.sourceLabel).join(", ")}</span>
        ) : null}
      </p>
    </ReviewItem>
  );
}

/**
 * Typed values extracted on every check (e.g. "Standard domestic fee"). A change in one of
 * these always passes the cheap noise filters, so they are the plan's sharpest signals.
 */
export function AttributesSection({ spec, onChange }: AttributesSectionProps) {
  const index = indexSpec(spec);
  return (
    <Section
      id="attributes"
      title={`Tracked values · ${spec.attributes.length}`}
      description="Specific values SignalLens extracts on every check and keeps a versioned history of. When one changes, you see the old and new value side by side."
    >
      {spec.attributes.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          No tracked values proposed. Pages will still be compared for meaningful changes.
        </p>
      ) : (
        <ul className="space-y-2">
          {spec.attributes.map((attribute, position) => (
            <AttributeItem
              key={`${attribute.entity_ref}:${attribute.key}:${position}`}
              attribute={attribute}
              position={position}
              index={index}
              onChange={onChange}
            />
          ))}
        </ul>
      )}
    </Section>
  );
}
