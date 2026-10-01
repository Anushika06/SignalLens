"use client";

import { useEffect, useState } from "react";
import { toast } from "sonner";
import { mutate } from "swr";

import { Section } from "@/components/common/page-header";
import { errorMessage } from "@/components/common/states";
import { CompanyProfileFields, EMPTY_PROFILE } from "@/components/profile/company-profile-fields";
import { Button } from "@/components/ui/button";
import { Field, FieldDescription, FieldError, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Separator } from "@/components/ui/separator";
import { Spinner } from "@/components/ui/spinner";
import { api, paths } from "@/lib/api";
import { revalidate } from "@/lib/hooks";
import type { CompanyProfile, WorkspaceDetail } from "@/lib/types";

type Draft = { name: string; profile: CompanyProfile };

function toDraft(workspace: WorkspaceDetail): Draft {
  return { name: workspace.name, profile: { ...EMPTY_PROFILE, ...workspace.profile } };
}

/** Accept "kivo.in" as well as "https://kivo.in"; blank means no website. */
function normalizeWebsite(value: string | null): string | null {
  const text = value?.trim() ?? "";
  if (!text) return null;
  return /^[a-z][a-z0-9+.-]*:\/\//i.test(text) ? text : `https://${text}`;
}

function isValidWebsite(value: string | null): boolean {
  const normalized = normalizeWebsite(value);
  if (!normalized) return true;
  try {
    const url = new URL(normalized);
    return (url.protocol === "https:" || url.protocol === "http:") && url.hostname.includes(".");
  } catch {
    return false;
  }
}

function cleanProfile(profile: CompanyProfile): CompanyProfile {
  return {
    company_name: profile.company_name.trim(),
    website: normalizeWebsite(profile.website),
    description: profile.description.trim(),
    products: profile.products,
    markets: profile.markets,
    competitors: profile.competitors,
    relationship_to_subjects: profile.relationship_to_subjects.trim(),
  };
}

/**
 * Workspace name and company profile ("us"). Changes are local until saved; leaving the page
 * with unsaved edits asks for confirmation.
 */
export function ProfileForm({ wid, workspace }: { wid: string; workspace: WorkspaceDetail }) {
  const [baseline, setBaseline] = useState<Draft>(() => toDraft(workspace));
  const [draft, setDraft] = useState<Draft>(baseline);
  const [saving, setSaving] = useState(false);
  const [submitted, setSubmitted] = useState(false);

  const dirty = JSON.stringify(draft) !== JSON.stringify(baseline);
  const nameError = draft.name.trim() ? null : "Give the workspace a name.";
  const websiteError = isValidWebsite(draft.profile.website) ? null : "Enter a valid website, e.g. https://kivo.in";

  useEffect(() => {
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent) => event.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  async function save(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitted(true);
    if (nameError || websiteError) return;
    setSaving(true);
    try {
      const updated = await api.workspaces.update(wid, { name: draft.name.trim(), profile: cleanProfile(draft.profile) });
      await mutate(paths.workspace(wid), updated, { revalidate: false });
      void revalidate((path) => path === paths.workspaces || path === paths.overview(wid));
      const next = toDraft(updated);
      setBaseline(next);
      setDraft(next);
      setSubmitted(false);
      toast.success("Company profile saved", {
        description: "New intelligence will be analysed against this profile.",
      });
    } catch (error) {
      toast.error("Couldn't save the profile", { description: errorMessage(error) });
    } finally {
      setSaving(false);
    }
  }

  return (
    <Section
      id="profile"
      title="Company profile"
      description="This is how SignalLens knows who “you” are. Impact analysis uses it to explain why a change matters to your company — not in general — and routing uses it together with your teams."
    >
      <form onSubmit={save} noValidate className="overflow-hidden rounded-xl border bg-card">
        <div className="space-y-6 p-4 sm:p-6">
          <Field data-invalid={submitted && nameError ? true : undefined} className="max-w-md">
            <FieldLabel htmlFor="workspace-name">Workspace name</FieldLabel>
            <Input
              id="workspace-name"
              value={draft.name}
              onChange={(event) => setDraft({ ...draft, name: event.target.value })}
              aria-invalid={submitted && nameError ? true : undefined}
              aria-describedby="workspace-name-hint"
              required
            />
            <FieldDescription id="workspace-name-hint">Shown in the sidebar and the workspace list.</FieldDescription>
            {submitted && nameError ? <FieldError>{nameError}</FieldError> : null}
          </Field>
          <Separator />
          <CompanyProfileFields
            idPrefix="settings-profile"
            value={draft.profile}
            onChange={(profile) => setDraft({ ...draft, profile })}
            disabled={saving}
          />
          {submitted && websiteError ? <FieldError>{websiteError}</FieldError> : null}
        </div>
        <div className="flex flex-col-reverse gap-3 border-t bg-muted/30 px-4 py-3 sm:flex-row sm:items-center sm:justify-between sm:px-6">
          <p className="text-xs text-muted-foreground" aria-live="polite">
            {dirty ? "You have unsaved changes." : "All changes saved."}
          </p>
          <div className="flex gap-2">
            <Button
              type="button"
              variant="outline"
              disabled={!dirty || saving}
              onClick={() => {
                setDraft(baseline);
                setSubmitted(false);
              }}
            >
              Reset
            </Button>
            <Button type="submit" disabled={!dirty || saving}>
              {saving ? <Spinner aria-hidden="true" /> : null}
              Save profile
            </Button>
          </div>
        </div>
      </form>
    </Section>
  );
}
