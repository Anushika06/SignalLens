"use client";

import { useState } from "react";
import { Mail, Pencil, Plus, Send, Trash2, Users } from "lucide-react";
import { toast } from "sonner";

import { Chip, ToneBadge, WithTooltip } from "@/components/common/badges";
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
import { Spinner } from "@/components/ui/spinner";
import { api, paths } from "@/lib/api";
import { humanize } from "@/lib/format";
import { revalidate, usePolicy, useSystemConfig, useTeams } from "@/lib/hooks";
import type { EmailConfig, EmailProvider, Team } from "@/lib/types";

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

const EMAIL_PROVIDER_LABEL: Record<EmailProvider, string> = { brevo: "Brevo", resend: "Resend", smtp: "SMTP" };

/** "Email: Brevo" / "Email: not configured" — which provider sends digests and alerts on this deployment. */
function EmailStatus({ email }: { email: EmailConfig | undefined }) {
  if (!email) return null;
  const label = email.configured && email.provider ? EMAIL_PROVIDER_LABEL[email.provider] : "not configured";
  const detail = email.configured
    ? `Sent from ${email.sender ?? "the configured sender"}.${email.digest_enabled ? "" : " The daily email digest is turned off."}`
    : (email.reason ?? "Ask an administrator to set BREVO_API_KEY, RESEND_API_KEY or SL_SMTP_HOST.");
  return (
    <WithTooltip content={detail} focusable>
      <span className="inline-flex items-center gap-1.5 text-xs text-muted-foreground">
        <Mail className="size-3.5" aria-hidden="true" />
        Email: <span className={email.configured ? "font-medium text-foreground" : undefined}>{label}</span>
      </span>
    </WithTooltip>
  );
}

function TestEmailButton({ wid, team, email }: { wid: string; team: Team; email: EmailConfig | undefined }) {
  const [sending, setSending] = useState(false);
  const recipients = team.emails ?? [];
  const disabledReason =
    recipients.length === 0
      ? "Add an email recipient first."
      : email && !email.configured
        ? "Email is not configured on this deployment."
        : null;

  async function send() {
    setSending(true);
    try {
      const result = await api.teams.testEmail(wid, team.id);
      if (result.delivered) {
        const via = result.provider ? ` via ${EMAIL_PROVIDER_LABEL[result.provider]}` : "";
        toast.success(`Test email sent${via}`, { description: `To ${result.recipients.join(", ")}` });
      } else {
        toast.error("The test email was not sent", { description: result.error ?? "Unknown error" });
      }
    } catch (error) {
      toast.error("Couldn't send the test email", { description: errorMessage(error) });
    } finally {
      setSending(false);
    }
  }

  const button = (
    <Button
      variant="ghost"
      size="sm"
      onClick={() => void send()}
      disabled={sending || disabledReason !== null}
      aria-label={`Send a test email to ${team.name}`}
    >
      {sending ? <Spinner aria-hidden="true" /> : <Send aria-hidden="true" />}
      Test email
    </Button>
  );
  // Disabled buttons don't fire pointer events; wrap so the tooltip still explains why.
  return disabledReason ? (
    <WithTooltip content={disabledReason}>
      <span tabIndex={0}>{button}</span>
    </WithTooltip>
  ) : (
    button
  );
}

type TeamRowProps = {
  wid: string;
  team: Team;
  teams: Team[];
  areaOptions: AreaOption[] | null;
  email: EmailConfig | undefined;
};

function TeamRow({ wid, team, teams, areaOptions, email }: TeamRowProps) {
  const emails = team.emails ?? [];
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
          {emails.length > 0 ? (
            <ToneBadge tone="green">
              {emails.length} email recipient{emails.length === 1 ? "" : "s"}
            </ToneBadge>
          ) : (
            <ToneBadge tone="gray">No email</ToneBadge>
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
          <dt className="text-xs text-muted-foreground sm:pt-0.5">Email to</dt>
          <dd className="flex flex-wrap gap-1">
            {emails.length === 0 ? (
              <span className="text-xs text-muted-foreground">Nobody — add recipients to get alerts and the digest by email</span>
            ) : (
              emails.map((address) => <Chip key={address}>{address}</Chip>)
            )}
          </dd>
        </dl>
      </div>
      <div className="flex shrink-0 flex-wrap gap-1">
        <TestEmailButton wid={wid} team={team} email={email} />
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
  const { data: config } = useSystemConfig();
  const email = config?.email;

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
      description="Each intelligence card is routed to the teams that own its area — critical and high severity right away (in-app, Slack and email), everything else in the daily digest."
      actions={teams && teams.length > 0 ? addButton : null}
    >
      {email ? (
        <div>
          <EmailStatus email={email} />
        </div>
      ) : null}
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
            <TeamRow key={team.id} wid={wid} team={team} teams={teams} areaOptions={areaOptions} email={email} />
          ))}
        </ul>
      )}
    </Section>
  );
}
