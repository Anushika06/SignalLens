"use client";

import { Archive, FilterX } from "lucide-react";

import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectSeparator, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { useEntities, usePolicy } from "@/lib/hooks";
import { ENTITY_ROLE, EVIDENCE, EVIDENCE_ORDER, SEVERITY, SEVERITY_ORDER, TONE_DOT, TONE_TEXT } from "@/lib/labels";
import type { FeedView } from "@/lib/routes";
import type { EntityRole, EntitySummary } from "@/lib/types";

import type { FeedFilters } from "./use-feed-filters";

/** Radix Select reserves "" for "no value", so "any" needs its own sentinel. */
const ANY = "__any";

type FilterOption = { value: string; label: string; icon?: React.ReactNode };

type FilterSelectProps = {
  label: string;
  value: string | undefined;
  options: FilterOption[];
  /** Shown when the URL holds a value the options don't know (yet). */
  unknownLabel?: string;
  onChange: (value: string | undefined) => void;
};

/** A compact select whose visible text doubles as its label: "Severity: High". */
function FilterSelect({ label, value, options, unknownLabel, onChange }: FilterSelectProps) {
  const known = value === undefined || options.some((option) => option.value === value);
  const items = known || value === undefined ? options : [...options, { value, label: unknownLabel ?? value }];
  return (
    <Select value={value ?? ANY} onValueChange={(next) => onChange(next === ANY ? undefined : next)}>
      <SelectTrigger
        aria-label={`${label} filter`}
        className={cn("w-full max-w-full min-w-0 sm:w-auto sm:max-w-72 sm:min-w-36", value !== undefined && "border-brand/40")}
      >
        <span className="shrink-0 text-muted-foreground">{label}:</span>
        <SelectValue className="min-w-0" />
      </SelectTrigger>
      <SelectContent position="popper" align="start">
        <SelectItem value={ANY}>Any</SelectItem>
        <SelectSeparator />
        {items.map((option) => (
          <SelectItem key={option.value} value={option.value}>
            {option.icon}
            {option.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

const ROLE_ORDER: EntityRole[] = ["subject", "competitor", "regulator", "partner", "us", "related"];

function byRoleThenName(a: EntitySummary, b: EntitySummary) {
  return ROLE_ORDER.indexOf(a.role) - ROLE_ORDER.indexOf(b.role) || a.name.localeCompare(b.name);
}

const SEVERITY_OPTIONS: FilterOption[] = SEVERITY_ORDER.map((severity) => ({
  value: severity,
  label: SEVERITY[severity].label,
  icon: <span aria-hidden="true" className={cn("size-2 rounded-full", TONE_DOT[SEVERITY[severity].tone])} />,
}));

const EVIDENCE_OPTIONS: FilterOption[] = EVIDENCE_ORDER.map((status) => {
  const meta = EVIDENCE[status];
  const Icon = meta.icon;
  return {
    value: status,
    label: meta.label,
    icon: Icon ? <Icon aria-hidden="true" className={TONE_TEXT[meta.tone]} /> : undefined,
  };
});

type FeedFilterBarProps = {
  wid: string;
  filters: FeedFilters;
  hasFilters: boolean;
  onChange: (changes: Partial<Record<keyof FeedFilters, string | undefined>>) => void;
  onClear: () => void;
};

/** Severity, area, entity and evidence-status filters for the intelligence feed. */
export function FeedFilterBar({ wid, filters, hasFilters, onChange, onClear }: FeedFilterBarProps) {
  // Areas come from the active monitoring policy; a workspace without one simply has no area filter.
  const { data: policy } = usePolicy(wid);
  const { data: entities } = useEntities(wid);

  const areaOptions: FilterOption[] = (policy?.areas ?? []).map((area) => ({ value: area.key, label: area.label }));
  const entityOptions: FilterOption[] = [...(entities ?? [])].sort(byRoleThenName).map((entity) => ({
    value: entity.id,
    label: entity.role === "subject" || entity.role === "us" ? `${entity.name} · ${ENTITY_ROLE[entity.role].label}` : entity.name,
  }));

  const showArea = areaOptions.length > 0 || filters.area !== undefined;
  const showEntity = entityOptions.length > 0 || filters.entity !== undefined;

  return (
    <div role="group" aria-label="Filter reports" className="grid grid-cols-1 gap-2 min-[420px]:grid-cols-2 sm:flex sm:flex-wrap sm:items-center">
      <FilterSelect
        label="Severity"
        value={filters.severity}
        options={SEVERITY_OPTIONS}
        onChange={(severity) => onChange({ severity })}
      />
      {showArea ? (
        <FilterSelect label="Area" value={filters.area} options={areaOptions} onChange={(area) => onChange({ area })} />
      ) : null}
      {showEntity ? (
        <FilterSelect
          label="Entity"
          value={filters.entity}
          options={entityOptions}
          unknownLabel="Selected entity"
          onChange={(entity) => onChange({ entity })}
        />
      ) : null}
      <FilterSelect
        label="Evidence"
        value={filters.evidence}
        options={EVIDENCE_OPTIONS}
        onChange={(evidence) => onChange({ evidence })}
      />
      {hasFilters ? (
        <Button variant="ghost" size="sm" onClick={onClear} className="justify-self-start">
          <FilterX aria-hidden="true" />
          Clear filters
        </Button>
      ) : null}
    </div>
  );
}

/** Live (new reports), Historical (web-archive backfill) or All. */
export function FeedViewToggle({ value, onChange }: { value: FeedView; onChange: (view: FeedView) => void }) {
  return (
    <ToggleGroup
      type="single"
      variant="outline"
      spacing={0}
      value={value}
      onValueChange={(next) => {
        if (next) onChange(next as FeedView);
      }}
      aria-label="Which reports to show"
    >
      <ToggleGroupItem value="live" className="px-3">
        Live
      </ToggleGroupItem>
      <ToggleGroupItem value="historical" className="px-3">
        <Archive aria-hidden="true" />
        Historical
      </ToggleGroupItem>
      <ToggleGroupItem value="all" className="px-3">
        All
      </ToggleGroupItem>
    </ToggleGroup>
  );
}
