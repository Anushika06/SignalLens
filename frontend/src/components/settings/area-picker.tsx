"use client";

import { TagInput } from "@/components/common/tag-input";
import { Checkbox } from "@/components/ui/checkbox";
import { FieldDescription, FieldLabel, FieldLegend, FieldSet } from "@/components/ui/field";
import { Label } from "@/components/ui/label";
import { humanize } from "@/lib/format";

export type AreaOption = { key: string; label: string };

type AreaPickerProps = {
  idPrefix: string;
  /** Selected area keys. Empty means "all areas". */
  value: string[];
  onChange: (next: string[]) => void;
  /** The active policy's areas, or null when there is no active plan yet. */
  options: AreaOption[] | null;
  disabled?: boolean;
};

/**
 * Which monitoring areas a team owns. With an active plan this is a checklist of its areas
 * ("All areas" = no specific areas); without one, area keys can be typed freely.
 */
export function AreaPicker({ idPrefix, value, onChange, options, disabled }: AreaPickerProps) {
  if (!options || options.length === 0) {
    return (
      <div className="space-y-2">
        <FieldLabel htmlFor={`${idPrefix}-areas`}>Areas this team owns</FieldLabel>
        <TagInput
          id={`${idPrefix}-areas`}
          value={value}
          onChange={onChange}
          placeholder="pricing, regulation…"
          disabled={disabled}
          aria-describedby={`${idPrefix}-areas-hint`}
        />
        <FieldDescription id={`${idPrefix}-areas-hint`}>
          There is no active monitoring plan yet, so type area keys. Leave empty to receive every area.
        </FieldDescription>
      </div>
    );
  }

  // Keep areas the team already has even if the current plan no longer includes them.
  const known = new Set(options.map((option) => option.key));
  const extra = value.filter((key) => !known.has(key)).map((key) => ({ key, label: humanize(key), stale: true }));
  const all = value.length === 0;

  function toggle(key: string, checked: boolean) {
    onChange(checked ? [...value, key] : value.filter((item) => item !== key));
  }

  return (
    <FieldSet className="gap-3">
      <FieldLegend variant="label">Areas this team owns</FieldLegend>
      <FieldDescription className="-mt-2">Leave “All areas” on for a team that should see everything.</FieldDescription>
      <div className="grid gap-2 rounded-lg border p-3 sm:grid-cols-2">
        <div className="flex items-center gap-2.5 sm:col-span-2">
          <Checkbox
            id={`${idPrefix}-area-all`}
            checked={all}
            onCheckedChange={(checked) => {
              // Picking a specific area turns "All areas" off; unchecking it alone is a no-op.
              if (checked === true) onChange([]);
            }}
            disabled={disabled}
          />
          <Label htmlFor={`${idPrefix}-area-all`} className="font-medium">
            All areas
          </Label>
        </div>
        {[...options.map((option) => ({ ...option, stale: false })), ...extra].map((option) => (
          <div key={option.key} className="flex items-center gap-2.5">
            <Checkbox
              id={`${idPrefix}-area-${option.key}`}
              checked={value.includes(option.key)}
              onCheckedChange={(checked) => toggle(option.key, checked === true)}
              disabled={disabled}
            />
            <Label htmlFor={`${idPrefix}-area-${option.key}`} className="min-w-0 font-normal">
              <span className="truncate">{option.label}</span>
              {option.stale ? <span className="text-xs text-muted-foreground">(not in current plan)</span> : null}
            </Label>
          </div>
        ))}
      </div>
    </FieldSet>
  );
}
