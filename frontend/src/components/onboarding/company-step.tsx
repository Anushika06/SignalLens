"use client";

import { Info, Target } from "lucide-react";

import { Section } from "@/components/common/page-header";
import { CompanyProfileFields } from "@/components/profile/company-profile-fields";
import { Field, FieldDescription, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import type { CompanyProfile } from "@/lib/types";

import type { TeamDraft } from "./default-teams";
import { TeamsEditor } from "./teams-editor";

type CompanyStepProps = {
  name: string;
  onNameChange: (name: string) => void;
  profile: CompanyProfile;
  onProfileChange: (profile: CompanyProfile) => void;
  teams: TeamDraft[];
  onTeamsChange: (teams: TeamDraft[]) => void;
  teamErrors: Record<string, string>;
  /** Set once the workspace exists (the plan call failed): edits here no longer apply. */
  createdWorkspaceName: string | null;
};

/** Step 1: who "us" is. Everything is optional; it is what makes impact analysis specific. */
export function CompanyStep({
  name,
  onNameChange,
  profile,
  onProfileChange,
  teams,
  onTeamsChange,
  teamErrors,
  createdWorkspaceName,
}: CompanyStepProps) {
  return (
    <div className="space-y-10">
      {createdWorkspaceName ? (
        <p className="flex gap-2 rounded-lg border bg-muted/40 p-3 text-sm text-pretty text-muted-foreground" role="note">
          <Info className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
          <span>
            The workspace “{createdWorkspaceName}” already exists, so changes here won&apos;t be saved. You can update
            the profile and teams later in Settings.
          </span>
        </p>
      ) : null}

      <div className="flex gap-3 rounded-xl border border-brand/20 bg-brand/5 p-4 text-sm">
        <Target className="mt-0.5 size-4 shrink-0 text-brand" aria-hidden="true" />
        <div className="space-y-1 text-pretty">
          <p className="font-medium">This is what lets SignalLens say why a change matters to you.</p>
          <p className="text-muted-foreground">
            The same competitor price cut is a threat to a rival gateway and leverage for a merchant who uses it.
            Everything here is optional, and you can edit it any time in Settings.
          </p>
        </div>
      </div>

      <Section id="workspace" title="Workspace">
        <Field>
          <FieldLabel htmlFor="workspace-name">Workspace name</FieldLabel>
          <Input
            id="workspace-name"
            value={name}
            onChange={(event) => onNameChange(event.target.value)}
            placeholder="Razorpay watch"
            aria-describedby="workspace-name-hint"
          />
          <FieldDescription id="workspace-name-hint">
            Leave it blank and we&apos;ll name it after what you monitor.
          </FieldDescription>
        </Field>
      </Section>

      <Section
        id="company"
        title="Your company"
        description="Used by impact analysis to explain each change in terms of your products, markets and competitors."
      >
        <CompanyProfileFields value={profile} onChange={onProfileChange} idPrefix="onboarding" />
      </Section>

      <Section
        id="teams"
        title="Teams"
        description="Each intelligence card goes to the teams that own its area. Leave a team's areas empty to send it everything."
      >
        <TeamsEditor teams={teams} onChange={onTeamsChange} errors={teamErrors} />
      </Section>
    </div>
  );
}
