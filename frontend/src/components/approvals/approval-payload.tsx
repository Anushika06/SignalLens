"use client";

import { ChevronDown } from "lucide-react";

import { JsonView } from "@/components/common/json-view";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import type { Approval } from "@/lib/types";

import { describePayload } from "./payload";

function HeaderRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="grid grid-cols-[4.5rem_1fr] gap-2 px-3 py-1.5 text-sm">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="min-w-0 break-words">{value}</dd>
    </div>
  );
}

/**
 * What exactly would leave the company if this is approved. Text is rendered as text —
 * agent-written content is never turned into links or HTML.
 */
export function ApprovalPayload({ approval }: { approval: Approval }) {
  const view = describePayload(approval);

  return (
    <div className="space-y-2">
      <p className="text-xs font-medium text-muted-foreground">
        {view.kind === "email"
          ? "Email to be sent"
          : view.kind === "share"
            ? "What will be shared"
            : view.kind === "webhook"
              ? "Request to be posted"
              : "Action details"}
      </p>

      {view.kind === "email" ? (
        <div className="overflow-hidden rounded-lg border bg-background">
          <dl className="divide-y border-b bg-muted/30">
            <HeaderRow label="To" value={view.to} />
            {view.cc ? <HeaderRow label="Cc" value={view.cc} /> : null}
            {view.subject ? <HeaderRow label="Subject" value={view.subject} /> : null}
          </dl>
          <div className="max-h-72 overflow-y-auto px-3 py-3 text-sm leading-relaxed whitespace-pre-wrap">
            {view.body ?? <span className="text-muted-foreground">No message body.</span>}
          </div>
        </div>
      ) : view.kind === "share" ? (
        <div className="overflow-hidden rounded-lg border bg-background">
          <dl className="divide-y">
            <HeaderRow label="Recipient" value={view.recipient} />
            {view.reportTitle ? <HeaderRow label="Card" value={view.reportTitle} /> : null}
            <HeaderRow label="Note" value={view.note ?? "No note"} />
          </dl>
        </div>
      ) : view.kind === "webhook" ? (
        <div className="space-y-2">
          <div className="overflow-hidden rounded-lg border bg-background">
            <dl>
              <div className="grid grid-cols-[4.5rem_1fr] gap-2 px-3 py-1.5 text-sm">
                <dt className="text-muted-foreground">POST to</dt>
                <dd className="min-w-0 font-mono text-xs break-all">{view.url}</dd>
              </div>
            </dl>
          </div>
          {view.body !== null ? <JsonView value={view.body} label="Webhook body" maxHeight={240} /> : null}
        </div>
      ) : (
        <JsonView value={approval.payload} label="Action payload" maxHeight={240} />
      )}

      {view.kind !== "raw" ? (
        <Collapsible>
          <CollapsibleTrigger className="group inline-flex items-center gap-1 rounded-sm text-xs text-muted-foreground outline-none hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring">
            Raw payload
            <ChevronDown className="size-3 transition-transform group-data-[state=open]:rotate-180" aria-hidden="true" />
          </CollapsibleTrigger>
          <CollapsibleContent className="mt-2">
            <JsonView value={approval.payload} label="Raw payload" maxHeight={240} />
          </CollapsibleContent>
        </Collapsible>
      ) : null}
    </div>
  );
}
