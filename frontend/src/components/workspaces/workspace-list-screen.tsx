"use client";

import Link from "next/link";
import { Plus, Radar } from "lucide-react";

import { PageHeader } from "@/components/common/page-header";
import { CardGridSkeleton } from "@/components/common/skeletons";
import { EmptyState, ErrorState } from "@/components/common/states";
import { SimpleShell } from "@/components/shell/simple-shell";
import { Button } from "@/components/ui/button";
import { useWorkspaces } from "@/lib/hooks";
import { routes } from "@/lib/routes";

import { WorkspaceCard } from "./workspace-card";

function NewWorkspaceButton() {
  return (
    <Button asChild>
      <Link href={routes.newWorkspace}>
        <Plus aria-hidden="true" />
        New workspace
      </Link>
    </Button>
  );
}

/** "/" — every workspace in the organisation, with what each one is monitoring and waiting on. */
export function WorkspaceListScreen() {
  const { data: workspaces, error, isLoading, mutate } = useWorkspaces();

  let content: React.ReactNode;
  if (error) {
    content = <ErrorState error={error} onRetry={() => void mutate()} />;
  } else if (isLoading || !workspaces) {
    content = <CardGridSkeleton count={3} />;
  } else if (workspaces.length === 0) {
    content = (
      <EmptyState
        icon={Radar}
        title="Create your first workspace"
        description={
          <>
            A workspace is one thing you want to keep an eye on — a competitor, a market or a regulator. Tell SignalLens
            what to watch; it researches the subject, proposes a monitoring plan for you to approve, then monitors it and
            tells you what materially changed.
          </>
        }
        action={<NewWorkspaceButton />}
        className="py-16"
      />
    );
  } else {
    content = (
      <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {workspaces.map((workspace) => (
          <li key={workspace.id}>
            <WorkspaceCard workspace={workspace} />
          </li>
        ))}
      </ul>
    );
  }

  return (
    <SimpleShell>
      <div className="space-y-8">
        <PageHeader
          title="Workspaces"
          description="Each workspace watches what you asked about — with its own approved plan, world state and intelligence feed."
          actions={workspaces && workspaces.length > 0 ? <NewWorkspaceButton /> : null}
        />
        {content}
      </div>
    </SimpleShell>
  );
}
