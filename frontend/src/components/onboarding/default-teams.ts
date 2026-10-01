import type { TeamInput } from "@/lib/types";

/** A team row being edited in onboarding (`key` is only a stable React key). */
export type TeamDraft = { key: string; name: string; areas: string[] };

/**
 * The teams a new workspace gets when `teams` is omitted (contract §4). Strategy owns "all
 * areas", which we represent as an empty `areas` list — an assumption, documented in the README.
 */
export const DEFAULT_TEAMS: TeamDraft[] = [
  { key: "strategy", name: "Strategy", areas: [] },
  { key: "product", name: "Product", areas: ["products", "pricing", "technology"] },
  { key: "compliance", name: "Compliance", areas: ["regulation", "legal"] },
  { key: "sales", name: "Sales & BD", areas: ["partnerships", "pricing", "customers"] },
  { key: "leadership", name: "Leadership", areas: ["funding", "leadership", "acquisitions"] },
];

let nextKey = 0;
export function newTeamKey() {
  nextKey += 1;
  return `team-${nextKey}`;
}

/** Area keys are lowercase words joined by underscores, e.g. "Customer success" → "customer_success". */
export function toAreaKey(value: string) {
  return value.trim().toLowerCase().replace(/\s+/g, "_");
}

function comparable(teams: TeamDraft[]) {
  return JSON.stringify(teams.map((team) => ({ name: team.name.trim(), areas: [...team.areas].sort() })));
}

/** Only send `teams` when the user actually changed the defaults; otherwise the backend applies them. */
export function teamsChanged(teams: TeamDraft[]) {
  return comparable(teams) !== comparable(DEFAULT_TEAMS);
}

export function toTeamInputs(teams: TeamDraft[]): TeamInput[] {
  return teams.map((team) => ({ name: team.name.trim(), areas: team.areas, members: [] }));
}

/** Validation messages keyed by team key: every team needs a unique name. */
export function teamErrors(teams: TeamDraft[]): Record<string, string> {
  const errors: Record<string, string> = {};
  const seen = new Set<string>();
  for (const team of teams) {
    const name = team.name.trim().toLowerCase();
    if (!name) errors[team.key] = "Name this team, or remove it.";
    else if (seen.has(name)) errors[team.key] = "Another team already has this name.";
    seen.add(name);
  }
  return errors;
}
