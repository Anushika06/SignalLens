"use client";

import { useState } from "react";
import { Pencil, Plus, Trash2, Users } from "lucide-react";
import { toast } from "sonner";

import { Chip, ToneBadge } from "@/components/common/badges";
import { Section } from "@/components/common/page-header";
import { ListSkeleton } from "@/components/common/skeletons";
import { EmptyState, ErrorState, errorMessage } from "@/components/common/states";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { api, paths } from "@/lib/api";
import { humanize } from "@/lib/format";
import { revalidate, usePolicy, useTeams } from "@/lib/hooks";
import type { Team } from "@/lib/types";

import type { AreaOption } from "./area-picker";
import { TeamDialog } from "./team-dialog";

function DeleteTeam({ wid, team }: { wid: string; team: Team }) {
  const [deleting, setDeleting] = useState(false);

  async function remove() {
    setDeleting(true);
    try {
      await api.teams.remove(wid, team.id);
      toast.success(`Deleted “${team.name}”`);
      await revalidate((path) => path === paths.teams(wid) || path === paths.workspace(wid));
    } catch (error) {
      toast.error("Couldn't delete the team", { description: errorMessage(error) });
    } finally {
      setDeleting(false);
    }
  }

  return (
    <AlertDialog>
      <AlertDialogTrigger asChild>
        <Button variant="ghost" size="icon-sm" aria-label={`Delete ${team.name}`} disabled={deleting}>
          <Trash2 aria-hidden="true" />
        </Button>
      </AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Delete “{team.name}”?</AlertDialogTitle>
          <AlertDialogDescription>
            The team and its Slack connection are removed, and it stops receiving new intelligence. Reports already
            delivered stay in the feed.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <AlertDialogAction variant="destructive" onClick={() => void remove()}>
            Delete team
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}

type TeamRowProps = {
  wid: string;
  team: Team;
  teams: Team[];
  areaOptions: AreaOption[] | null;
};

function TeamRow({ wid, team, teams, areaOptions }: TeamRowProps) {
  const areaLabel = (key: string) => areaOptions?.find((option) => option.key === key)?.label ?? humanize(key);
  const otherNames = teams.filter((other) => other.id !== team.id).map((other) => other.name);

  return (
    <li className="flex flex-col gap-3 px-4 py-4 sm:flex-row sm:items-start sm:gap-6 sm:px-5">
      <div className="min-w-0 flex-1 space-y-2.5">
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="text-sm font-semibold">{team.name}</h3>
          {team.slack_configured ? (
            <ToneBadge tone="green">Slack connected</ToneBadge>
          ) : (
            <ToneBadge tone="gray">No Slack</ToneBadge>
          )}
        </div>
        <dl className="grid gap-2 text-sm sm:grid-cols-[5.5rem_1fr]">
          <dt className="text-xs text-muted-foreground sm:pt-0.5">Areas</dt>
          <dd className="flex flex-wrap gap-1">
            {team.areas.length === 0 ? (
              <Chip className="border-brand/25 text-brand">All areas</Chip>
            ) : (
              team.areas.map((key) => <Chip key={key}>{areaLabel(key)}</Chip>)
            )}
          </dd>
          <dt className="text-xs text-muted-foreground sm:pt-0.5">Members</dt>
          <dd className="flex flex-wrap gap-1">
            {team.members.length === 0 ? (
              <span className="text-xs text-muted-foreground">No members yet</span>
            ) : (
              team.members.map((member) => <Chip key={member}>{member}</Chip>)
            )}
          </dd>
        </dl>
      </div>
      <div className="flex shrink-0 gap-1">
        <TeamDialog
          wid={wid}
          team={team}
          areaOptions={areaOptions}
          otherNames={otherNames}
          trigger={
            <Button variant="outline" size="sm">
              <Pencil aria-hidden="true" />
              Edit
            </Button>
          }
        />
        <DeleteTeam wid={wid} team={team} />
      </div>
    </li>
  );
}

/** Teams decide who hears about what: each owns some monitoring areas and may have a Slack channel. */
export function TeamsSection({ wid }: { wid: string }) {
  const { data: teams, error, isLoading, mutate } = useTeams(wid);
  // 404 = no active monitoring plan yet; the area picker then falls back to free text.
  const { data: policy } = usePolicy(wid);
  const areaOptions: AreaOption[] | null = policy ? policy.areas.map(({ key, label }) => ({ key, label })) : null;

  const addButton = (
    <TeamDialog
      wid={wid}
      areaOptions={areaOptions}
      otherNames={(teams ?? []).map((team) => team.name)}
      trigger={
        <Button size="sm">
          <Plus aria-hidden="true" />
          Add team
        </Button>
      }
    />
  );

  return (
    <Section
      id="teams"
      title="Teams"
      description="Each intelligence card is routed to the teams that own its area — critical and high severity right away (in-app and Slack), everything else in the daily digest."
      actions={teams && teams.length > 0 ? addButton : null}
    >
      {error && !teams ? (
        <ErrorState error={error} onRetry={() => void mutate()} />
      ) : isLoading || !teams ? (
        <ListSkeleton rows={3} />
      ) : teams.length === 0 ? (
        <EmptyState
          icon={Users}
          title="No teams yet"
          description="Without teams, intelligence stays in the feed and nobody is notified. Add the teams that own pricing, product, compliance and so on."
          action={addButton}
        />
      ) : (
        <ul className="divide-y rounded-xl border bg-card">
          {teams.map((team) => (
            <TeamRow key={team.id} wid={wid} team={team} teams={teams} areaOptions={areaOptions} />
          ))}
        </ul>
      )}
    </Section>
  );
}
