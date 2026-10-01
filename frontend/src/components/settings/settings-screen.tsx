"use client";

import { PageHeader } from "@/components/common/page-header";
import { ErrorState } from "@/components/common/states";
import { Skeleton } from "@/components/ui/skeleton";
import { useWorkspace } from "@/lib/hooks";

import { MembersSection } from "./members-section";
import { ProfileForm } from "./profile-form";
import { TeamsSection } from "./teams-section";

function ProfileSkeleton() {
  return (
    <div className="space-y-3" aria-busy="true" aria-label="Loading">
      <Skeleton className="h-4 w-40" />
      <div className="space-y-5 rounded-xl border p-6">
        <Skeleton className="h-8 w-full max-w-md" />
        <div className="grid gap-5 sm:grid-cols-2">
          <Skeleton className="h-8" />
          <Skeleton className="h-8" />
        </div>
        <Skeleton className="h-20" />
      </div>
    </div>
  );
}

/** Workspace settings: who "we" are (company profile), who hears about what (teams), who approves (members). */
export function SettingsScreen({ wid }: { wid: string }) {
  const { data: workspace, error, isLoading, mutate } = useWorkspace(wid);

  return (
    <div className="max-w-4xl space-y-10">
      <PageHeader
        title="Settings"
        description="Tell SignalLens who you are and who should hear about what. Both shape every intelligence card from here on."
      />
      {error && !workspace ? (
        <ErrorState error={error} onRetry={() => void mutate()} />
      ) : isLoading || !workspace ? (
        <ProfileSkeleton />
      ) : (
        <ProfileForm key={workspace.id} wid={wid} workspace={workspace} />
      )}
      <TeamsSection wid={wid} />
      <MembersSection wid={wid} />
    </div>
  );
}
