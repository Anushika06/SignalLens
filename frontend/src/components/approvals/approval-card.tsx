"use client";

import Link from "next/link";
import { ChevronDown } from "lucide-react";

import { MetaBadge } from "@/components/common/badges";
import { JsonView } from "@/components/common/json-view";
import { RelativeTime } from "@/components/common/relative-time";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { isAgentName } from "@/components/runs/agent-icon";
import { AGENT, APPROVAL_ACTION, APPROVAL_STATUS } from "@/lib/labels";
import { routes } from "@/lib/routes";
import type { Approval } from "@/lib/types";

import { ApprovalPayload } from "./approval-payload";
import { DecisionDialog } from "./decision-dialog";
import { resultError } from "./payload";

/** "Proposed by the Impact analyst" for agents, "Requested by a team member" for people. */
function requester(requestedBy: string) {
  if (isAgentName(requestedBy)) return { agent: true, text: `Proposed by the ${AGENT[requestedBy].label} agent` };
  if (requestedBy === "user") return { agent: false, text: "Requested by a team member" };
  return { agent: false, text: `Requested by ${requestedBy}` };
}

function DecidedFooter({ approval }: { approval: Approval }) {
  const error = resultError(approval);
  return (
    <footer className="space-y-2 border-t bg-muted/30 px-4 py-3 text-sm sm:px-5">
      <p className="text-muted-foreground">
        {APPROVAL_STATUS[approval.status].label}
        {approval.decided_by ? <> · decided by {approval.decided_by}</> : null}
        {approval.decided_at ? (
          <>
            {" "}
            · <RelativeTime value={approval.decided_at} />
          </>
        ) : null}
      </p>
      {approval.decision_note ? (
        <p className="text-sm text-pretty">
          <span className="text-muted-foreground">Decision note: </span>
          {approval.decision_note}
        </p>
      ) : null}
      {error ? <p className="text-sm text-destructive">{error}</p> : null}
      {approval.result ? (
        <Collapsible>
          <CollapsibleTrigger className="group inline-flex items-center gap-1 rounded-sm text-xs text-muted-foreground outline-none hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring">
            What happened
            <ChevronDown className="size-3 transition-transform group-data-[state=open]:rotate-180" aria-hidden="true" />
          </CollapsibleTrigger>
          <CollapsibleContent className="mt-2">
            <JsonView value={approval.result} label="Result" maxHeight={220} />
          </CollapsibleContent>
        </Collapsible>
      ) : null}
    </footer>
  );
}

/**
 * One proposed external action: what it is, who proposed it and why, exactly what would be
 * sent — and, while pending, the Approve / Reject decision.
 */
export function ApprovalCard({ wid, approval }: { wid: string; approval: Approval }) {
  const action = APPROVAL_ACTION[approval.action_type];
  const Icon = action.icon;
  const titleId = `approval-${approval.id}-title`;
  const who = requester(approval.requested_by);
  const pending = approval.status === "pending";

  return (
    <article aria-labelledby={titleId} className="overflow-hidden rounded-xl border bg-card">
      <div className="space-y-4 p-4 sm:p-5">
        <header className="flex flex-wrap items-start justify-between gap-3">
          <div className="flex min-w-0 items-start gap-3">
            <span
              aria-hidden="true"
              className="flex size-9 shrink-0 items-center justify-center rounded-lg border bg-muted/60 text-muted-foreground"
            >
              {Icon ? <Icon className="size-4" /> : null}
            </span>
            <div className="min-w-0 space-y-1">
              <p className="text-xs font-medium text-muted-foreground">{action.label}</p>
              <h3 id={titleId} className="text-base leading-snug font-semibold text-pretty">
                {approval.title}
              </h3>
              <p className="flex flex-wrap items-center gap-x-1.5 gap-y-0.5 text-xs text-muted-foreground">
                <span>{who.text}</span>
                <span aria-hidden="true">·</span>
                <RelativeTime value={approval.created_at} />
                {approval.report_id ? (
                  <>
                    <span aria-hidden="true">·</span>
                    <Link
                      href={routes.report(wid, approval.report_id)}
                      className="font-medium text-foreground/80 underline-offset-4 hover:text-brand hover:underline"
                    >
                      Open the intelligence card
                    </Link>
                  </>
                ) : null}
              </p>
            </div>
          </div>
          <MetaBadge meta={APPROVAL_STATUS[approval.status]} tooltip={false} />
        </header>

        {approval.reason ? (
          <div className="rounded-lg bg-muted/50 px-3 py-2.5">
            <p className="text-xs font-medium text-muted-foreground">
              {who.agent ? "Why the agent proposes this" : "Reason"}
            </p>
            <p className="mt-1 text-sm leading-relaxed text-pretty">{approval.reason}</p>
          </div>
        ) : null}

        <ApprovalPayload approval={approval} />
      </div>

      {pending ? (
        <footer className="flex flex-col gap-3 border-t bg-muted/30 px-4 py-3 sm:flex-row sm:items-center sm:justify-between sm:px-5">
          <p className="text-xs text-muted-foreground">Nothing is sent until someone approves.</p>
          <div className="flex gap-2">
            <DecisionDialog wid={wid} approval={approval} decision="reject" />
            <DecisionDialog wid={wid} approval={approval} decision="approve" />
          </div>
        </footer>
      ) : (
        <DecidedFooter approval={approval} />
      )}
    </article>
  );
}
