import { Chip, MetaBadge } from "@/components/common/badges";
import { ExternalLink } from "@/components/common/links";
import { Section } from "@/components/common/page-header";
import { ENTITY_KIND, ENTITY_ROLE } from "@/lib/labels";
import type { MonitoringPlan, PlanEntity } from "@/lib/types";

import { ReviewItem, WhyLine } from "./review-item";

type EntitiesSectionProps = {
  spec: MonitoringPlan;
  onChange: (ref: string, patch: Partial<PlanEntity>) => void;
};

function EntityItem({ entity, onChange }: { entity: PlanEntity; onChange: EntitiesSectionProps["onChange"] }) {
  return (
    <ReviewItem
      title={entity.name}
      badges={
        <>
          <MetaBadge meta={ENTITY_ROLE[entity.role]} />
          <Chip>{ENTITY_KIND[entity.kind].label}</Chip>
        </>
      }
      enabled={entity.enabled}
      onEnabledChange={(enabled) => onChange(entity.ref, { enabled })}
      switchLabel={`Monitor ${entity.name}`}
      level={4}
    >
      {entity.description ? <p className="text-sm text-pretty">{entity.description}</p> : null}
      {entity.official_domains.length > 0 ? (
        <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
          <span>Official domains:</span>
          {entity.official_domains.map((domain) => (
            <ExternalLink key={domain} href={`https://${domain}`} className="font-medium text-foreground/80">
              {domain}
            </ExternalLink>
          ))}
        </p>
      ) : null}
      {entity.aliases.length > 0 ? (
        <p className="text-xs text-muted-foreground">Also known as {entity.aliases.join(", ")}</p>
      ) : null}
      <WhyLine reason={entity.reason} />
    </ReviewItem>
  );
}

/** Subjects first, then the related companies, products and regulators around them. */
export function EntitiesSection({ spec, onChange }: EntitiesSectionProps) {
  const subjects = spec.entities.filter((entity) => entity.role === "subject");
  const related = spec.entities.filter((entity) => entity.role !== "subject");
  const groups = [
    { key: "subjects", title: "Subjects", items: subjects },
    { key: "related", title: "Related", items: related },
  ].filter((group) => group.items.length > 0);

  return (
    <Section
      id="entities"
      title={`Entities · ${spec.entities.length}`}
      description="Who this plan watches. Turning an entity off also skips its sources and tracked values. Official domains decide which sources count as primary evidence."
    >
      {spec.entities.length === 0 ? (
        <p className="text-sm text-muted-foreground">The planner didn&apos;t propose any entities.</p>
      ) : (
        <div className="space-y-5">
          {groups.map((group) => (
            <div key={group.key} className="space-y-2">
              <h3 className="text-xs font-medium tracking-wide text-muted-foreground uppercase">{group.title}</h3>
              <ul className="space-y-2">
                {group.items.map((entity) => (
                  <EntityItem key={entity.ref} entity={entity} onChange={onChange} />
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}
    </Section>
  );
}
