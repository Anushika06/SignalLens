"use client";

import { Plus, RotateCcw, Trash2 } from "lucide-react";

import { TagInput } from "@/components/common/tag-input";
import { Button } from "@/components/ui/button";
import { Field, FieldError, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";

import { DEFAULT_TEAMS, newTeamKey, type TeamDraft, teamsChanged, toAreaKey } from "./default-teams";

type TeamsEditorProps = {
  teams: TeamDraft[];
  onChange: (teams: TeamDraft[]) => void;
  /** Validation messages by team key (shown after the user tries to continue). */
  errors: Record<string, string>;
};

/**
 * The workspace's teams as editable rows: a name and the monitoring areas the team owns.
 * An empty area list means the team hears about every area.
 */
export function TeamsEditor({ teams, onChange, errors }: TeamsEditorProps) {
  const update = (key: string, patch: Partial<TeamDraft>) =>
    onChange(teams.map((team) => (team.key === key ? { ...team, ...patch } : team)));

  return (
    <div className="space-y-3">
      <div className="overflow-hidden rounded-xl border bg-card">
        <div
          aria-hidden="true"
          className="hidden grid-cols-[minmax(0,11rem)_minmax(0,1fr)_2rem] gap-3 border-b bg-muted/40 px-3 py-2 text-xs font-medium text-muted-foreground sm:grid"
        >
          <span>Team</span>
          <span>Areas it owns</span>
          <span />
        </div>
        {teams.length === 0 ? (
          <p className="px-4 py-6 text-center text-sm text-muted-foreground">
            No teams. Intelligence will still reach your inbox, but nothing is routed to a team.
          </p>
        ) : (
          <ul className="divide-y">
            {teams.map((team) => {
              const error = errors[team.key];
              const label = team.name.trim() || "this team";
              return (
                <li
                  key={team.key}
                  className="grid gap-2 p-3 sm:grid-cols-[minmax(0,11rem)_minmax(0,1fr)_2rem] sm:items-start sm:gap-3"
                >
                  <Field data-invalid={error ? true : undefined} className="gap-1.5">
                    <FieldLabel htmlFor={`${team.key}-name`} className="text-xs sm:sr-only">
                      Team name
                    </FieldLabel>
                    <Input
                      id={`${team.key}-name`}
                      value={team.name}
                      onChange={(event) => update(team.key, { name: event.target.value })}
                      placeholder="Team name"
                      aria-invalid={error ? true : undefined}
                      aria-describedby={error ? `${team.key}-error` : undefined}
                    />
                    {error ? <FieldError id={`${team.key}-error`}>{error}</FieldError> : null}
                  </Field>
                  <Field className="gap-1.5">
                    <FieldLabel htmlFor={`${team.key}-areas`} className="text-xs sm:sr-only">
                      Areas {label} owns
                    </FieldLabel>
                    <TagInput
                      id={`${team.key}-areas`}
                      value={team.areas}
                      onChange={(areas) => update(team.key, { areas: areas.map(toAreaKey).filter(Boolean) })}
                      placeholder="All areas"
                    />
                  </Field>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon-sm"
                    className="justify-self-end text-muted-foreground sm:mt-0.5"
                    aria-label={`Remove ${label}`}
                    onClick={() => onChange(teams.filter((item) => item.key !== team.key))}
                  >
                    <Trash2 aria-hidden="true" />
                  </Button>
                </li>
              );
            })}
          </ul>
        )}
      </div>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => onChange([...teams, { key: newTeamKey(), name: "", areas: [] }])}
        >
          <Plus aria-hidden="true" />
          Add team
        </Button>
        {teamsChanged(teams) ? (
          <Button type="button" variant="ghost" size="sm" onClick={() => onChange(DEFAULT_TEAMS)}>
            <RotateCcw aria-hidden="true" />
            Restore the defaults
          </Button>
        ) : null}
      </div>
    </div>
  );
}
