import Link from "next/link";
import { ArrowRight, Share2 } from "lucide-react";

import { MetaBadge } from "@/components/common/badges";
import { RelativeTime } from "@/components/common/relative-time";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { AGENT, APPROVAL_ACTION, APPROVAL_STATUS } from "@/lib/labels";
import { routes } from "@/lib/routes";
import type { AgentName, Approval } from "@/lib/types";

function requesterLabel(requestedBy: string) {
  if (requestedBy === "user") return "Requested by a person";
  if (requestedBy in AGENT) return `Proposed by the ${AGENT[requestedBy as AgentName].label.toLowerCase()}`;
  return `Requested by ${requestedBy}`;
}

function recipientOf(approval: Approval): string | null {
  const { recipient, to } = approval.payload;
  if (typeof recipient === "string") return recipient;
  if (typeof to === "string") return to;
  return null;
}

function ApprovalLine({ approval }: { approval: Approval }) {
  const action = APPROVAL_ACTION[approval.action_type];
  const Icon = action.icon;
  const recipient = recipientOf(approval);
  return (
    <li className="rounded-lg border p-2.5">
      <div className="flex items-start gap-2">
        {Icon ? <Icon className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden="true" /> : null}
        <div className="min-w-0 flex-1 space-y-1">
          <p className="text-sm leading-snug font-medium text-pretty">{approval.title}</p>
          {recipient ? <p className="truncate text-xs text-muted-foreground">To {recipient}</p> : null}
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
            <MetaBadge meta={APPROVAL_STATUS[approval.status]} tooltip={false} />
            {approval.decided_at ? (
              <span>
                {approval.decided_by ? `${approval.decided_by} · ` : null}
                <RelativeTime value={approval.decided_at} />
              </span>
            ) : (
              <span>
                {requesterLabel(approval.requested_by)} · <RelativeTime value={approval.created_at} />
              </span>
            )}
          </div>
        </div>
      </div>
    </li>
  );
}

type ExternalSharingCardProps = {
  wid: string;
  approvals: Approval[];
  onShare: () => void;
};

/** External actions proposed for this card (by the agent or a person) and their decisions. */
export function ExternalSharingCard({ wid, approvals, onShare }: ExternalSharingCardProps) {
  const pending = approvals.filter((approval) => approval.status === "pending").length;
  return (
    <Card size="sm">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Share2 className="size-4 text-muted-foreground" aria-hidden="true" />
          External sharing
        </CardTitle>
        <CardDescription>Nothing leaves SignalLens without a human decision.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {approvals.length > 0 ? (
          <ul className="space-y-2" aria-label="Share requests for this card">
            {approvals.map((approval) => (
              <ApprovalLine key={approval.id} approval={approval} />
            ))}
          </ul>
        ) : (
          <p className="text-sm text-muted-foreground">No share requests for this card yet.</p>
        )}
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" size="sm" onClick={onShare}>
            Share externally…
          </Button>
          {approvals.length > 0 ? (
            <Button asChild variant="ghost" size="sm">
              <Link href={routes.approvals(wid)}>
                {pending > 0 ? `Decide in Approvals (${pending})` : "Open Approvals"}
                <ArrowRight aria-hidden="true" />
              </Link>
            </Button>
          ) : null}
        </div>
      </CardContent>
    </Card>
  );
}
