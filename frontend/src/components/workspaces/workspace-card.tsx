import Link from "next/link";

import { cn } from "@/lib/utils";
import { Chip, MetaBadge } from "@/components/common/badges";
import { formatDate, formatNumber } from "@/lib/format";
import { WORKSPACE_STATUS } from "@/lib/labels";
import { routes } from "@/lib/routes";
import type { WorkspaceStatus, WorkspaceSummary } from "@/lib/types";

/** What, if anything, the workspace is waiting on — shown so the next action is obvious. */
const STATUS_HINT: Partial<Record<WorkspaceStatus, string>> = {
  setup: "Needs a monitoring plan",
  planning: "The planner is researching your request",
  awaiting_approval: "A monitoring plan is waiting for your review",
  baselining: "Recording the baseline — no alerts yet",
  paused: "Monitoring is paused",
};

const MAX_SUBJECTS = 4;

export function WorkspaceCard({ workspace }: { workspace: WorkspaceSummary }) {
  const hint = STATUS_HINT[workspace.status];
  const extraSubjects = workspace.subjects.length - MAX_SUBJECTS;

  return (
    <Link
      href={routes.dashboard(workspace.id)}
      className="group flex h-full flex-col gap-4 rounded-xl border bg-card p-5 transition-[border-color,box-shadow] hover:border-foreground/20 hover:shadow-sm focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none"
    >
      <div className="flex items-start justify-between gap-3">
        <h2 className="min-w-0 text-base leading-snug font-semibold tracking-tight text-balance group-hover:text-brand">
          {workspace.name}
        </h2>
        <MetaBadge meta={WORKSPACE_STATUS[workspace.status]} tooltip={false} className="shrink-0" />
      </div>

      <div className="space-y-1.5">
        <p className="text-xs text-muted-foreground">Monitoring</p>
        {workspace.subjects.length > 0 ? (
          <div className="flex flex-wrap gap-1.5">
            {workspace.subjects.slice(0, MAX_SUBJECTS).map((subject) => (
              <Chip key={subject} className="text-foreground">
                {subject}
              </Chip>
            ))}
            {extraSubjects > 0 ? <Chip>+{extraSubjects} more</Chip> : null}
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">No subjects yet</p>
        )}
      </div>

      {hint ? <p className="text-sm text-pretty text-brand">{hint}</p> : null}

      <div className="mt-auto flex flex-wrap items-center justify-between gap-2 border-t pt-3 text-xs text-muted-foreground">
        <span
          className={cn("inline-flex items-center gap-1.5", workspace.unread_reports > 0 && "font-medium text-foreground")}
        >
          {workspace.unread_reports > 0 ? (
            <>
              <span aria-hidden="true" className="size-1.5 rounded-full bg-brand" />
              <span className="metric">{formatNumber(workspace.unread_reports)}</span> unread
            </>
          ) : (
            "No unread intelligence"
          )}
        </span>
        <span>Created {formatDate(workspace.created_at)}</span>
      </div>
    </Link>
  );
}
