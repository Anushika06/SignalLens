"use client";

import { useState } from "react";
import { toast } from "sonner";

import { AreaChip } from "@/components/common/badges";
import { DefinitionList } from "@/components/common/page-header";
import { RelativeTime } from "@/components/common/relative-time";
import { errorMessage } from "@/components/common/states";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { CHECK_INTERVAL_OPTIONS, formatInterval, formatNumber } from "@/lib/format";
import { PRIORITY, PRIORITY_ORDER } from "@/lib/labels";
import type { Priority, SourcePatch, SourceView } from "@/lib/types";

import { useSourceUpdate } from "./source-actions";
import { SourceChecks } from "./source-checks";

/** Base interval and priority, saved as soon as they change (PATCH /sources/{sid}). */
function SourceSchedule({ wid, source, idPrefix }: { wid: string; source: SourceView; idPrefix: string }) {
  const update = useSourceUpdate(wid);
  const [saving, setSaving] = useState(false);
  const options = (CHECK_INTERVAL_OPTIONS as readonly number[]).includes(source.check_every_hours)
    ? [...CHECK_INTERVAL_OPTIONS]
    : [...CHECK_INTERVAL_OPTIONS, source.check_every_hours].sort((a, b) => a - b);
  const intervalId = `${idPrefix}-interval-${source.id}`;
  const priorityId = `${idPrefix}-priority-${source.id}`;

  async function save(patch: SourcePatch, message: string) {
    setSaving(true);
    try {
      await update(source.id, patch);
      toast.success(message);
    } catch (error) {
      toast.error("Couldn't save the change", { description: errorMessage(error) });
    } finally {
      setSaving(false);
    }
  }

  return (
    <fieldset className="space-y-3" disabled={saving}>
      <legend className="text-xs font-medium text-muted-foreground">Schedule</legend>
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-1.5">
          <Label htmlFor={intervalId}>Base interval</Label>
          <Select
            value={String(source.check_every_hours)}
            onValueChange={(value) =>
              void save(
                { check_every_hours: Number(value) },
                `Base interval set to ${formatInterval(Number(value)).toLowerCase()}`,
              )
            }
            disabled={saving}
          >
            <SelectTrigger id={intervalId} className="w-full bg-background">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {options.map((hours) => (
                <SelectItem key={hours} value={String(hours)}>
                  {formatInterval(hours)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor={priorityId}>Priority</Label>
          <Select
            value={source.priority}
            onValueChange={(value) =>
              void save({ priority: value as Priority }, `Priority set to ${PRIORITY[value as Priority].label.toLowerCase()}`)
            }
            disabled={saving}
          >
            <SelectTrigger id={priorityId} className="w-full bg-background">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {PRIORITY_ORDER.map((priority) => (
                <SelectItem key={priority} value={priority}>
                  {PRIORITY[priority].label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>
      <p className="text-xs text-pretty text-muted-foreground">
        Changes apply from the next check. SignalLens checks more often after a change and backs off while the source
        stays quiet.
      </p>
    </fieldset>
  );
}

type SourceDetailsProps = {
  wid: string;
  source: SourceView;
  areaLabel: (key: string) => string;
  /** Keeps form ids unique: the table and the card layout can both be in the DOM. */
  idPrefix: string;
};

/** Expanded view of a source: why it is monitored, its schedule and its recent checks. */
export function SourceDetails({ wid, source, areaLabel, idPrefix }: SourceDetailsProps) {
  return (
    <div className="grid gap-6 p-4 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
      <div className="min-w-0 space-y-5">
        <div className="space-y-1">
          <h3 className="text-xs font-medium text-muted-foreground">Why this source</h3>
          <p className="text-sm text-pretty">{source.reason || "The planner didn't record a reason."}</p>
        </div>
        <DefinitionList
          items={[
            {
              label: "Areas",
              value:
                source.areas.length > 0 ? (
                  <span className="flex flex-wrap gap-1">
                    {source.areas.map((area) => (
                      <AreaChip key={area} label={areaLabel(area)} />
                    ))}
                  </span>
                ) : (
                  <span className="text-muted-foreground">None</span>
                ),
            },
            { label: "Snapshots stored", value: <span className="metric">{formatNumber(source.snapshots)}</span> },
            {
              label: "Last change",
              value: source.last_changed_at ? (
                <RelativeTime value={source.last_changed_at} />
              ) : (
                <span className="text-muted-foreground">No change seen yet</span>
              ),
            },
            {
              label: "History backfill",
              value:
                source.kind === "news" ? (
                  <span className="text-muted-foreground">Not available for news</span>
                ) : source.backfill ? (
                  "On — the past year was replayed from the web archive"
                ) : (
                  "Off"
                ),
            },
          ]}
        />
        <SourceSchedule wid={wid} source={source} idPrefix={idPrefix} />
      </div>
      <div className="min-w-0 space-y-2">
        <h3 className="text-xs font-medium text-muted-foreground">Recent checks</h3>
        <SourceChecks wid={wid} sid={source.id} />
      </div>
    </div>
  );
}
