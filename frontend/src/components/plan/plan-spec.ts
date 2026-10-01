/**
 * Pure helpers for reviewing a MonitoringPlan: which items are effectively on, why an item
 * will be skipped, what the user changed, and the spec that is sent on approval.
 */
import { humanize, prettyUrl } from "@/lib/format";
import type { MonitoringPlan, PlanAttribute, PlanAttributeValueType, PlanSource } from "@/lib/types";

export type SpecIndex = {
  entityOn: (ref: string) => boolean;
  areaOn: (key: string) => boolean;
  entityName: (ref: string) => string;
  areaLabel: (key: string) => string;
  sourceLabel: (ref: string) => string;
};

export function indexSpec(spec: MonitoringPlan): SpecIndex {
  const entities = new Map(spec.entities.map((entity) => [entity.ref, entity]));
  const areas = new Map(spec.areas.map((area) => [area.key, area]));
  const sources = new Map(spec.sources.map((source) => [source.ref, source]));
  return {
    // Unknown references are treated as "on": only an explicit switch turns something off.
    entityOn: (ref) => entities.get(ref)?.enabled ?? true,
    areaOn: (key) => areas.get(key)?.enabled ?? true,
    entityName: (ref) => entities.get(ref)?.name ?? humanize(ref),
    areaLabel: (key) => areas.get(key)?.label ?? humanize(key),
    sourceLabel: (ref) => {
      const source = sources.get(ref);
      if (!source) return humanize(ref);
      return source.kind === "page" ? prettyUrl(source.url) || source.ref : `News: “${source.query ?? source.ref}”`;
    },
  };
}

/** Why an attribute that is switched on will still be skipped (its entity or area is off). */
export function attributeSkipReason(attribute: PlanAttribute, index: SpecIndex): string | null {
  if (!index.entityOn(attribute.entity_ref)) return `${index.entityName(attribute.entity_ref)} is turned off`;
  if (!index.areaOn(attribute.area)) return `the ${index.areaLabel(attribute.area)} area is turned off`;
  return null;
}

/** Why a source that is switched on will still be skipped (its entity, or every one of its areas, is off). */
export function sourceSkipReason(source: PlanSource, index: SpecIndex): string | null {
  if (!index.entityOn(source.entity_ref)) return `${index.entityName(source.entity_ref)} is turned off`;
  if (source.areas.length > 0 && !source.areas.some(index.areaOn)) {
    return source.areas.length === 1
      ? `the ${index.areaLabel(source.areas[0])} area is turned off`
      : "all of its areas are turned off";
  }
  return null;
}

export type PlanCounts = { entities: number; areas: number; sources: number; attributes: number };

/** What will actually be monitored if the plan is approved as it stands. */
export function countEffective(spec: MonitoringPlan): PlanCounts {
  const index = indexSpec(spec);
  return {
    entities: spec.entities.filter((entity) => entity.enabled).length,
    areas: spec.areas.filter((area) => area.enabled).length,
    sources: spec.sources.filter((source) => source.enabled && !sourceSkipReason(source, index)).length,
    attributes: spec.attributes.filter((attribute) => attribute.enabled && !attributeSkipReason(attribute, index))
      .length,
  };
}

/**
 * The spec sent with "Approve": sources and tracked values that are skipped because their
 * entity or area is off are explicitly disabled, so the backend never has to infer it.
 */
export function specForApproval(spec: MonitoringPlan): MonitoringPlan {
  const index = indexSpec(spec);
  return {
    ...spec,
    attributes: spec.attributes.map((attribute) => ({
      ...attribute,
      enabled: attribute.enabled && !attributeSkipReason(attribute, index),
    })),
    sources: spec.sources.map((source) => ({ ...source, enabled: source.enabled && !sourceSkipReason(source, index) })),
  };
}

/** Number of entities, areas, tracked values and sources that differ from the planner's proposal. */
export function countEdits(original: MonitoringPlan, current: MonitoringPlan): number {
  const changed = <T>(before: T[], after: T[]) =>
    after.reduce((total, item, i) => total + (JSON.stringify(item) === JSON.stringify(before[i]) ? 0 : 1), 0);
  return (
    changed(original.entities, current.entities) +
    changed(original.areas, current.areas) +
    changed(original.attributes, current.attributes) +
    changed(original.sources, current.sources)
  );
}

export const VALUE_TYPE_LABEL: Record<PlanAttributeValueType, string> = {
  percent: "Percentage",
  money: "Amount",
  number: "Number",
  text: "Text",
  list: "List",
  date: "Date",
  boolean: "Yes / no",
};
