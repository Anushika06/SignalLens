import type { EntityRole, EntitySummary } from "@/lib/types";

/** Display order and headings for entity groups: what you monitor first, context last. */
export const ROLE_GROUPS: { role: EntityRole; title: string; description?: string }[] = [
  { role: "subject", title: "Subjects", description: "What you asked SignalLens to monitor." },
  { role: "competitor", title: "Competitors" },
  { role: "regulator", title: "Regulators" },
  { role: "partner", title: "Partners" },
  { role: "us", title: "Your company", description: "Used to explain why a change matters to you." },
  { role: "related", title: "Related", description: "Products, organisations and topics that give context." },
];

/** Case-insensitive match on name, aliases, official domains and description. */
export function matchesEntity(entity: EntitySummary, query: string): boolean {
  const needle = query.trim().toLowerCase();
  if (!needle) return true;
  return [entity.name, entity.description, ...entity.aliases, ...entity.official_domains].some((text) =>
    text.toLowerCase().includes(needle),
  );
}
