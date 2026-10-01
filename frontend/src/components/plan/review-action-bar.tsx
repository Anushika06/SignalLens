"use client";

import { Check, CloudAlert, RotateCcw } from "lucide-react";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { plural } from "@/lib/format";

import type { PlanCounts } from "./plan-spec";
import type { DraftState } from "./use-draft-autosave";

type ReviewActionBarProps = {
  counts: PlanCounts;
  edits: number;
  draft: DraftState;
  busy: "approve" | "reject" | null;
  onResetEdits: () => void;
  onApprove: () => void;
  onReject: () => void;
};

function DraftStatus({ state }: { state: DraftState }) {
  if (state === "saving") {
    return (
      <span className="inline-flex items-center gap-1">
        <Spinner className="size-3" /> Saving draft…
      </span>
    );
  }
  if (state === "saved") {
    return (
      <span className="inline-flex items-center gap-1">
        <Check className="size-3" aria-hidden="true" /> Draft saved
      </span>
    );
  }
  if (state === "error") {
    return (
      <span className="inline-flex items-center gap-1 text-amber-700 dark:text-amber-300">
        <CloudAlert className="size-3" aria-hidden="true" /> Draft not saved — your edits are still sent when you approve
      </span>
    );
  }
  return null;
}

/**
 * Sticky footer of the plan review: what will be monitored if you approve now, what you
 * changed (with a one-click undo), and the two decisions.
 */
export function ReviewActionBar({ counts, edits, draft, busy, onResetEdits, onApprove, onReject }: ReviewActionBarProps) {
  const noSources = counts.sources === 0;
  return (
    <div className="sticky bottom-0 z-20 -mx-4 mt-10 border-t bg-background/95 px-4 py-3 backdrop-blur supports-backdrop-filter:bg-background/85 sm:-mx-6 sm:px-6 lg:-mx-8 lg:px-8">
      <div className="mx-auto flex max-w-5xl flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <div className="min-w-0 space-y-1">
          <p className="metric text-sm font-medium">
            {plural(counts.entities, "entity", "entities")} · {plural(counts.areas, "area")} ·{" "}
            {plural(counts.sources, "source")} · {plural(counts.attributes, "tracked value")}
          </p>
          <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground" aria-live="polite">
            {edits > 0 ? (
              <span className="inline-flex items-center gap-2">
                {plural(edits, "change")} to the proposal
                <Button type="button" variant="link" size="xs" className="h-auto px-0 text-xs" onClick={onResetEdits}>
                  <RotateCcw aria-hidden="true" />
                  Undo all
                </Button>
              </span>
            ) : (
              <span>No changes to the proposal</span>
            )}
            <DraftStatus state={draft} />
          </p>
          {noSources ? (
            <p className="text-xs font-medium text-destructive">Turn on at least one source to start monitoring.</p>
          ) : null}
        </div>
        <div className="flex gap-2">
          <AlertDialog>
            <AlertDialogTrigger asChild>
              <Button type="button" variant="outline" className="flex-1 md:flex-none" disabled={busy !== null}>
                {busy === "reject" ? <Spinner /> : null}
                Reject
              </Button>
            </AlertDialogTrigger>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>Reject this plan?</AlertDialogTitle>
                <AlertDialogDescription>
                  SignalLens won&apos;t monitor anything from it. You can start a new plan with a refined request straight
                  away.
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>Keep reviewing</AlertDialogCancel>
                <AlertDialogAction variant="destructive" onClick={onReject}>
                  Reject plan
                </AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
          <Button type="button" className="flex-[2] md:flex-none" onClick={onApprove} disabled={busy !== null || noSources}>
            {busy === "approve" ? <Spinner /> : null}
            Approve &amp; start monitoring
          </Button>
        </div>
      </div>
    </div>
  );
}
