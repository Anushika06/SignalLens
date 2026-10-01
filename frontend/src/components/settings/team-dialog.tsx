"use client";

import { useState } from "react";
import { CheckCircle2, Unplug } from "lucide-react";
import { toast } from "sonner";

import { TagInput } from "@/components/common/tag-input";
import { errorMessage } from "@/components/common/states";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Field, FieldDescription, FieldError, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Spinner } from "@/components/ui/spinner";
import { api, paths } from "@/lib/api";
import { revalidate } from "@/lib/hooks";
import type { Team, TeamInput } from "@/lib/types";

import { AreaPicker, type AreaOption } from "./area-picker";

/**
 * Slack webhook edits are write-only: a stored URL is never shown. "keep" leaves it as is,
 * "set" sends a new URL (typed in the field), "clear" disconnects (sends null).
 */
type SlackMode = "keep" | "set" | "clear";

function slackUrlError(url: string): string | null {
  if (!url.trim()) return null;
  try {
    const parsed = new URL(url.trim());
    if (parsed.protocol !== "https:") return "The webhook URL must start with https://";
    return null;
  } catch {
    return "Enter a full webhook URL, e.g. https://hooks.slack.com/services/…";
  }
}

const EMAIL_RE = /^[^@\s<>()[\],;:"]+@[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?)+$/;

/** Mirrors the backend check, so a typo is caught before saving. */
function emailsError(emails: string[]): string | null {
  const bad = emails.filter((email) => !EMAIL_RE.test(email.trim()));
  if (bad.length === 0) return null;
  return bad.length === 1 ? `“${bad[0]}” is not a valid email address.` : `${bad.length} addresses are not valid: ${bad.join(", ")}`;
}

type TeamDialogProps = {
  wid: string;
  /** Present when editing; absent when creating. */
  team?: Team;
  areaOptions: AreaOption[] | null;
  /** Names of the other teams, to prevent duplicates. */
  otherNames: string[];
  trigger: React.ReactNode;
};

export function TeamDialog({ wid, team, areaOptions, otherNames, trigger }: TeamDialogProps) {
  const [open, setOpen] = useState(false);
  const editing = Boolean(team);
  const idPrefix = `team-${team?.id ?? "new"}`;

  const [name, setName] = useState(team?.name ?? "");
  const [areas, setAreas] = useState<string[]>(team?.areas ?? []);
  const [members, setMembers] = useState<string[]>(team?.members ?? []);
  const [emails, setEmails] = useState<string[]>(team?.emails ?? []);
  const [slackMode, setSlackMode] = useState<SlackMode>(team?.slack_configured ? "keep" : "set");
  const [slackUrl, setSlackUrl] = useState("");
  const [saving, setSaving] = useState(false);
  const [submitted, setSubmitted] = useState(false);

  function reset() {
    setName(team?.name ?? "");
    setAreas(team?.areas ?? []);
    setMembers(team?.members ?? []);
    setEmails(team?.emails ?? []);
    setSlackMode(team?.slack_configured ? "keep" : "set");
    setSlackUrl("");
    setSubmitted(false);
  }

  const trimmed = name.trim();
  const nameError = !trimmed
    ? "Give the team a name."
    : otherNames.some((other) => other.toLowerCase() === trimmed.toLowerCase())
      ? "Another team already has this name."
      : null;
  const urlError = slackMode === "set" ? slackUrlError(slackUrl) : null;
  const emailError = emailsError(emails);

  function body(): TeamInput | Partial<TeamInput> {
    const input: Partial<TeamInput> = { name: trimmed, areas, members, emails };
    if (slackMode === "set" && slackUrl.trim()) input.slack_webhook_url = slackUrl.trim();
    if (slackMode === "clear") input.slack_webhook_url = null;
    return input;
  }

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitted(true);
    if (nameError || urlError || emailError) return;
    setSaving(true);
    try {
      if (team) {
        await api.teams.update(wid, team.id, body());
        toast.success(`Saved “${trimmed}”`);
      } else {
        await api.teams.create(wid, body() as TeamInput);
        toast.success(`Created “${trimmed}”`, { description: "It will receive intelligence for its areas from now on." });
      }
      setOpen(false);
      await revalidate((path) => path === paths.teams(wid) || path === paths.workspace(wid));
    } catch (error) {
      toast.error(team ? "Couldn't save the team" : "Couldn't create the team", { description: errorMessage(error) });
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (saving) return;
        if (next) reset();
        setOpen(next);
      }}
    >
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent className="max-h-[90svh] overflow-y-auto sm:max-w-lg">
        <form onSubmit={submit} noValidate className="grid gap-5">
          <DialogHeader>
            <DialogTitle>{editing ? `Edit ${team?.name}` : "Add a team"}</DialogTitle>
            <DialogDescription>
              Intelligence in a team&apos;s areas is routed to it: critical and high severity right away, everything
              else in the daily digest.
            </DialogDescription>
          </DialogHeader>

          <FieldGroup className="gap-5">
            <Field data-invalid={submitted && nameError ? true : undefined}>
              <FieldLabel htmlFor={`${idPrefix}-name`}>Team name</FieldLabel>
              <Input
                id={`${idPrefix}-name`}
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder="Product marketing"
                aria-invalid={submitted && nameError ? true : undefined}
                autoFocus
              />
              {submitted && nameError ? <FieldError>{nameError}</FieldError> : null}
            </Field>

            <AreaPicker idPrefix={idPrefix} value={areas} onChange={setAreas} options={areaOptions} disabled={saving} />

            <Field>
              <FieldLabel htmlFor={`${idPrefix}-members`}>Members</FieldLabel>
              <TagInput
                id={`${idPrefix}-members`}
                value={members}
                onChange={setMembers}
                placeholder="Name or email, then Enter"
                disabled={saving}
              />
            </Field>

            <Field data-invalid={emailError && submitted ? true : undefined}>
              <FieldLabel htmlFor={`${idPrefix}-emails`}>Email recipients</FieldLabel>
              <TagInput
                id={`${idPrefix}-emails`}
                value={emails}
                onChange={setEmails}
                placeholder="name@company.com, then Enter"
                disabled={saving}
                aria-describedby={`${idPrefix}-emails-hint`}
                aria-invalid={submitted && emailError ? true : undefined}
              />
              <FieldDescription id={`${idPrefix}-emails-hint`}>
                Critical and high severity changes are emailed right away; everything else arrives in one daily digest
                email.
              </FieldDescription>
              {submitted && emailError ? <FieldError>{emailError}</FieldError> : null}
            </Field>

            <Field data-invalid={urlError && submitted ? true : undefined}>
              <FieldLabel htmlFor={`${idPrefix}-slack`}>Slack</FieldLabel>
              {slackMode === "keep" ? (
                <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg border px-3 py-2">
                  <span className="flex items-center gap-2 text-sm">
                    <CheckCircle2 className="size-4 text-emerald-600 dark:text-emerald-400" aria-hidden="true" />
                    Connected
                  </span>
                  <span className="flex gap-1">
                    <Button type="button" variant="ghost" size="sm" onClick={() => setSlackMode("set")}>
                      Replace URL
                    </Button>
                    <Button type="button" variant="ghost" size="sm" onClick={() => setSlackMode("clear")}>
                      <Unplug aria-hidden="true" />
                      Disconnect
                    </Button>
                  </span>
                </div>
              ) : slackMode === "clear" ? (
                <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-dashed px-3 py-2">
                  <span className="text-sm text-muted-foreground">Slack will be disconnected when you save.</span>
                  <Button type="button" variant="ghost" size="sm" onClick={() => setSlackMode("keep")}>
                    Undo
                  </Button>
                </div>
              ) : (
                <>
                  <Input
                    id={`${idPrefix}-slack`}
                    type="url"
                    inputMode="url"
                    autoComplete="off"
                    value={slackUrl}
                    onChange={(event) => setSlackUrl(event.target.value)}
                    placeholder="https://hooks.slack.com/services/…"
                    aria-invalid={submitted && urlError ? true : undefined}
                    aria-describedby={`${idPrefix}-slack-hint`}
                  />
                  {team?.slack_configured ? (
                    <Button
                      type="button"
                      variant="link"
                      size="xs"
                      className="w-fit px-0"
                      onClick={() => {
                        setSlackMode("keep");
                        setSlackUrl("");
                      }}
                    >
                      Keep the current webhook
                    </Button>
                  ) : null}
                </>
              )}
              <FieldDescription id={`${idPrefix}-slack-hint`}>
                An incoming-webhook URL for the team&apos;s channel. It is stored securely and never shown again.
              </FieldDescription>
              {submitted && urlError ? <FieldError>{urlError}</FieldError> : null}
            </Field>
          </FieldGroup>

          <DialogFooter>
            <DialogClose asChild>
              <Button type="button" variant="outline" disabled={saving}>
                Cancel
              </Button>
            </DialogClose>
            <Button type="submit" disabled={saving}>
              {saving ? <Spinner aria-hidden="true" /> : null}
              {editing ? "Save team" : "Add team"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
