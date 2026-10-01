"use client";

import { useId, useState } from "react";
import { useRouter } from "next/navigation";
import { ShieldCheck } from "lucide-react";
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
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Spinner } from "@/components/ui/spinner";
import { Textarea } from "@/components/ui/textarea";
import { api, paths } from "@/lib/api";
import { revalidate } from "@/lib/hooks";
import { routes } from "@/lib/routes";
import type { ReportDetail } from "@/lib/types";

type ShareDialogProps = {
  wid: string;
  report: Pick<ReportDetail, "id" | "title">;
  open: boolean;
  onOpenChange: (open: boolean) => void;
};

/**
 * Sharing is a consequential action, so this never sends anything: it creates a pending
 * approval (POST /reports/{rid}/share) that a person must approve before the report leaves.
 */
export function ShareDialog({ wid, report, open, onOpenChange }: ShareDialogProps) {
  const router = useRouter();
  const recipientId = useId();
  const noteId = useId();
  const errorId = useId();
  const [recipient, setRecipient] = useState("");
  const [note, setNote] = useState("");
  const [touched, setTouched] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const missingRecipient = touched && !recipient.trim();

  function reset() {
    setRecipient("");
    setNote("");
    setTouched(false);
    setError(null);
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setTouched(true);
    if (!recipient.trim()) return;
    setSubmitting(true);
    setError(null);
    try {
      await api.reports.share(wid, report.id, { recipient: recipient.trim(), note: note.trim() || undefined });
      toast.success("Sent for human approval", {
        description: "Nothing is shared until someone approves it in Approvals.",
        action: { label: "View", onClick: () => router.push(routes.approvals(wid)) },
      });
      reset();
      onOpenChange(false);
      void revalidate(paths.report(wid, report.id));
      void revalidate(paths.approvals(wid));
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) reset();
        onOpenChange(next);
      }}
    >
      <DialogContent className="sm:max-w-md">
        <form onSubmit={submit} noValidate className="grid gap-4">
          <DialogHeader>
            <DialogTitle>Share externally</DialogTitle>
            <DialogDescription>
              This creates a request in Approvals. The report is shared only after someone on your team approves it.
            </DialogDescription>
          </DialogHeader>

          <div className="rounded-lg border bg-muted/40 p-3">
            <p className="text-xs text-muted-foreground">Intelligence card</p>
            <p className="mt-0.5 text-sm font-medium text-pretty">{report.title}</p>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor={recipientId}>Recipient</Label>
            <Input
              id={recipientId}
              value={recipient}
              onChange={(event) => setRecipient(event.target.value)}
              onBlur={() => setTouched(true)}
              placeholder="name@company.com"
              autoComplete="email"
              required
              aria-invalid={missingRecipient || undefined}
              aria-describedby={missingRecipient ? errorId : undefined}
            />
            {missingRecipient ? (
              <p id={errorId} className="text-xs text-destructive">
                Add who this should go to.
              </p>
            ) : null}
          </div>

          <div className="space-y-1.5">
            <Label htmlFor={noteId}>
              Note <span className="font-normal text-muted-foreground">(optional)</span>
            </Label>
            <Textarea
              id={noteId}
              value={note}
              onChange={(event) => setNote(event.target.value)}
              rows={3}
              maxLength={2000}
              placeholder="Context for the recipient and for whoever approves this."
            />
          </div>

          <p className="flex items-start gap-2 text-xs text-pretty text-muted-foreground">
            <ShieldCheck className="mt-0.5 size-3.5 shrink-0 text-brand" aria-hidden="true" />
            SignalLens never takes external actions without a human decision.
          </p>

          {error ? (
            <p role="alert" className="text-sm text-destructive">
              {error}
            </p>
          ) : null}

          <DialogFooter>
            <DialogClose asChild>
              <Button type="button" variant="outline">
                Cancel
              </Button>
            </DialogClose>
            <Button type="submit" disabled={submitting}>
              {submitting ? <Spinner /> : null}
              Request approval
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
