"use client";

import { useState } from "react";
import { Check, X } from "lucide-react";
import { toast } from "sonner";

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
import { Field, FieldDescription, FieldLabel } from "@/components/ui/field";
import { Spinner } from "@/components/ui/spinner";
import { Textarea } from "@/components/ui/textarea";
import { api, isApiError, paths } from "@/lib/api";
import { revalidate } from "@/lib/hooks";
import { APPROVAL_ACTION } from "@/lib/labels";
import type { Approval, ApprovalDecision } from "@/lib/types";

import { approveConsequence, approveVerb, resultError } from "./payload";

/** Refresh everything that shows approval state: the queues, the report, the dashboard callout. */
async function refreshAfterDecision(wid: string, approval: Approval) {
  await Promise.all([
    revalidate(`${paths.workspace(wid)}/approvals`),
    revalidate((path) => path === paths.overview(wid)),
    approval.report_id ? revalidate((path) => path === paths.report(wid, approval.report_id!)) : null,
  ]);
}

function announce(decided: Approval, decision: ApprovalDecision) {
  const action = APPROVAL_ACTION[decided.action_type].label;
  if (decision === "reject") {
    toast.success("Rejected", { description: "Nothing was sent. The request stays in Decided for the record." });
  } else if (decided.status === "failed") {
    toast.error("Approved, but the action failed", {
      description: resultError(decided) ?? "See the Decided tab for details.",
    });
  } else if (decided.status === "executed") {
    toast.success("Approved and done", { description: `${action} completed.` });
  } else {
    toast.success("Approved", { description: `${action} will run now.` });
  }
}

type DecisionDialogProps = {
  wid: string;
  approval: Approval;
  decision: ApprovalDecision;
  /** The viewer may not decide (not an owner/admin, or their own request). */
  disabled?: boolean;
  /** Id of the element explaining why it's disabled. */
  describedBy?: string;
};

/**
 * Confirm an approve/reject decision. States the consequence in plain words and lets the
 * decider leave an optional note that is recorded with the decision.
 */
export function DecisionDialog({ wid, approval, decision, disabled = false, describedBy }: DecisionDialogProps) {
  const [open, setOpen] = useState(false);
  const [note, setNote] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const approve = decision === "approve";
  const noteId = `decision-note-${approval.id}-${decision}`;

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    try {
      const decided = await api.approvals.decide(wid, approval.id, { decision, note: note.trim() || undefined });
      announce(decided, decision);
      setOpen(false);
      setNote("");
      await refreshAfterDecision(wid, approval);
    } catch (error) {
      toast.error(approve ? "Couldn't approve" : "Couldn't reject", { description: errorMessage(error) });
      // 409: someone else decided first; 403: roles changed. Either way, show the current state.
      if (isApiError(error) && (error.status === 409 || error.status === 403)) {
        setOpen(false);
        await refreshAfterDecision(wid, approval);
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={(next) => (submitting ? undefined : setOpen(next))}>
      <DialogTrigger asChild>
        <Button
          variant={approve ? "default" : "outline"}
          size="sm"
          className="flex-1 sm:flex-none"
          disabled={disabled}
          aria-describedby={describedBy}
        >
          {approve ? <Check aria-hidden="true" /> : <X aria-hidden="true" />}
          {approve ? "Approve" : "Reject"}
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-md">
        <form onSubmit={submit} className="grid gap-4">
          <DialogHeader>
            <DialogTitle>{approve ? "Approve this action?" : "Reject this action?"}</DialogTitle>
            <DialogDescription className="text-pretty">
              {approve
                ? approveConsequence(approval)
                : "Nothing will be sent. The request moves to Decided so there is a record of it."}
            </DialogDescription>
          </DialogHeader>
          <p className="rounded-lg border bg-muted/40 px-3 py-2 text-sm font-medium text-pretty">{approval.title}</p>
          <Field>
            <FieldLabel htmlFor={noteId}>
              Note <span className="font-normal text-muted-foreground">(optional)</span>
            </FieldLabel>
            <Textarea
              id={noteId}
              value={note}
              onChange={(event) => setNote(event.target.value)}
              rows={3}
              placeholder={approve ? "Checked with legal — fine to send." : "Not the right audience for this."}
              aria-describedby={`${noteId}-hint`}
            />
            <FieldDescription id={`${noteId}-hint`}>Recorded with your decision.</FieldDescription>
          </Field>
          <DialogFooter>
            <DialogClose asChild>
              <Button type="button" variant="outline" disabled={submitting}>
                Cancel
              </Button>
            </DialogClose>
            <Button type="submit" variant={approve ? "default" : "destructive"} disabled={submitting}>
              {submitting ? <Spinner aria-hidden="true" /> : null}
              {approve ? approveVerb(approval) : "Reject"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
