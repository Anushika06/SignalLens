"use client";

import { useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { AlertTriangle, ArrowLeft, ArrowRight } from "lucide-react";

import { PageHeader } from "@/components/common/page-header";
import { errorMessage } from "@/components/common/states";
import { EMPTY_PROFILE, hasProfileContent } from "@/components/profile/company-profile-fields";
import { SimpleShell } from "@/components/shell/simple-shell";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { api, paths } from "@/lib/api";
import { revalidate } from "@/lib/hooks";
import { routes } from "@/lib/routes";
import type { CompanyProfile, CreateWorkspaceInput } from "@/lib/types";

import { CompanyStep } from "./company-step";
import { DEFAULT_TEAMS, type TeamDraft, teamErrors, teamsChanged, toTeamInputs } from "./default-teams";
import { deriveWorkspaceName } from "./derive-name";
import { RequestStep } from "./request-step";
import { StepIndicator } from "./step-indicator";

const STEPS = ["Your company", "What to monitor"];

const STEP_COPY = [
  {
    title: "About your company",
    description: "Tell SignalLens who “us” is, so every card can explain why a change matters to you.",
  },
  {
    title: "What should SignalLens monitor?",
    description: "Describe it in plain language. The planner turns it into a monitoring plan for you to approve.",
  },
];

function cleanProfile(profile: CompanyProfile): CompanyProfile {
  return {
    ...profile,
    company_name: profile.company_name.trim(),
    website: profile.website?.trim() || null,
    description: profile.description.trim(),
    relationship_to_subjects: profile.relationship_to_subjects.trim(),
  };
}

/**
 * /new — create a workspace in two steps, then start the planner and open the plan page.
 * If the workspace is created but the plan call fails, a retry only repeats the plan call.
 */
export function OnboardingWizard() {
  const router = useRouter();
  const headingRef = useRef<HTMLDivElement>(null);

  const [step, setStep] = useState(0);
  const [name, setName] = useState("");
  const [profile, setProfile] = useState<CompanyProfile>(EMPTY_PROFILE);
  const [teams, setTeams] = useState<TeamDraft[]>(DEFAULT_TEAMS);
  const [showTeamErrors, setShowTeamErrors] = useState(false);
  const [request, setRequest] = useState("");
  const [requestError, setRequestError] = useState<string | null>(null);
  const [created, setCreated] = useState<{ id: string; name: string } | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const errors = teamErrors(teams);
  const hasTeamErrors = Object.keys(errors).length > 0;
  const derivedName = name.trim() ? null : deriveWorkspaceName(request) || null;

  function goTo(next: number) {
    setStep(next);
    window.scrollTo({ top: 0 });
    requestAnimationFrame(() => headingRef.current?.focus());
  }

  function continueToRequest() {
    if (hasTeamErrors && !created) {
      setShowTeamErrors(true);
      const first = teams.find((team) => errors[team.key]);
      if (first) document.getElementById(`${first.key}-name`)?.focus();
      return;
    }
    goTo(1);
  }

  async function submit() {
    const requestText = request.trim();
    if (requestText.length < 3) {
      setRequestError("Tell SignalLens what to monitor. A company name is enough.");
      document.getElementById("monitoring-request")?.focus();
      return;
    }
    setRequestError(null);
    setSubmitError(null);
    setSubmitting(true);

    let workspace = created;
    try {
      if (!workspace) {
        const body: CreateWorkspaceInput = { name: name.trim() || deriveWorkspaceName(requestText) || "New workspace" };
        if (hasProfileContent(profile)) body.profile = cleanProfile(profile);
        if (teamsChanged(teams)) body.teams = toTeamInputs(teams);
        const detail = await api.workspaces.create(body);
        workspace = { id: detail.id, name: detail.name };
        setCreated(workspace);
        void revalidate(paths.workspaces);
      }
      const plan = await api.plans.create(workspace.id, { request_text: requestText });
      router.push(routes.plan(workspace.id, plan.id));
    } catch (error) {
      setSubmitError(errorMessage(error));
      setSubmitting(false);
    }
  }

  const copy = STEP_COPY[step];

  return (
    <SimpleShell width="narrow">
      <div className="space-y-8">
        <div className="space-y-6">
          <StepIndicator steps={STEPS} current={step} onSelect={goTo} />
          <div ref={headingRef} tabIndex={-1} className="outline-none">
            <PageHeader title={copy.title} description={copy.description} />
          </div>
        </div>

        {step === 0 ? (
          <CompanyStep
            name={name}
            onNameChange={setName}
            profile={profile}
            onProfileChange={setProfile}
            teams={teams}
            onTeamsChange={setTeams}
            teamErrors={showTeamErrors ? errors : {}}
            createdWorkspaceName={created?.name ?? null}
          />
        ) : (
          <RequestStep
            value={request}
            onChange={(value) => {
              setRequest(value);
              if (requestError) setRequestError(null);
            }}
            error={requestError}
            derivedName={created ? null : derivedName}
            onSubmitShortcut={() => void submit()}
          />
        )}

        {submitError ? (
          <Alert variant="destructive">
            <AlertTriangle aria-hidden="true" />
            <AlertTitle>{created ? "Your workspace is ready, but the planner couldn't start" : "Couldn't create the workspace"}</AlertTitle>
            <AlertDescription>
              <p>{submitError}</p>
              {created ? (
                <p>
                  Trying again only starts the plan; nothing is created twice.{" "}
                  <Link href={routes.dashboard(created.id)} className="underline underline-offset-4">
                    Open “{created.name}”
                  </Link>
                </p>
              ) : null}
            </AlertDescription>
          </Alert>
        ) : null}

        <footer className="flex flex-col-reverse gap-2 border-t pt-6 sm:flex-row sm:items-center sm:justify-between">
          {step === 0 ? (
            <>
              <Button asChild variant="ghost">
                <Link href={routes.home}>Cancel</Link>
              </Button>
              <div className="flex flex-col-reverse gap-2 sm:flex-row">
                {!hasProfileContent(profile) ? (
                  <Button type="button" variant="outline" onClick={continueToRequest}>
                    Skip for now
                  </Button>
                ) : null}
                <Button type="button" onClick={continueToRequest}>
                  Continue
                  <ArrowRight aria-hidden="true" />
                </Button>
              </div>
            </>
          ) : (
            <>
              <Button type="button" variant="ghost" onClick={() => goTo(0)} disabled={submitting}>
                <ArrowLeft aria-hidden="true" />
                Back
              </Button>
              <Button type="button" size="lg" onClick={() => void submit()} disabled={submitting}>
                {submitting ? <Spinner /> : null}
                {created ? "Try starting the plan again" : "Start research"}
              </Button>
            </>
          )}
        </footer>
      </div>
    </SimpleShell>
  );
}
