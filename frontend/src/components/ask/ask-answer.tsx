"use client";

import { useState } from "react";
import Link from "next/link";
import { AlertTriangle, ChevronDown, CornerDownRight, Globe, ListTree, RotateCcw, ShieldCheck } from "lucide-react";

import { RelativeTime } from "@/components/common/relative-time";
import { useAreaLabels } from "@/components/monitoring/use-area-labels";
import { RunStatusBadge } from "@/components/runs/run-status-badge";
import { RunTrace } from "@/components/runs/run-trace";
import { UsageInline } from "@/components/runs/run-usage";
import { useElapsed } from "@/components/plan/use-elapsed";
import { FactDrawer } from "@/components/world/fact-drawer";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Skeleton } from "@/components/ui/skeleton";
import { Spinner } from "@/components/ui/spinner";
import { formatDuration, plural } from "@/lib/format";
import { isRunActive, useAsk, useFact } from "@/lib/hooks";
import { routes } from "@/lib/routes";
import type { AskCitation, AskItem, RunStep } from "@/lib/types";

import { AnswerMarkdown } from "./answer-markdown";
import { CitationMarker, SourceList } from "./citations";

/** What the agent is doing right now, in words, from its latest step. */
function liveLabel(steps: RunStep[] | undefined, queued: boolean): string {
  if (queued) return "Waiting for a worker to pick up the question…";
  const last = steps?.at(-1);
  if (!last) return "Reading the question…";
  if (last.kind === "decision") {
    switch (last.name) {
      case "search_memory":
        return "Searching memory…";
      case "recent_changes":
        return "Looking at recent changes…";
      case "get_card":
        return "Reading an intelligence card…";
      case "get_fact_history":
        return "Reading a fact's history…";
      case "list_entities":
        return "Listing monitored entities…";
      case "web_search":
        return "Searching the web (outside memory)…";
      case "finish":
        return "Checking citations…";
    }
  }
  return "Thinking about what to look at next…";
}

/** A fact citation opens the fact's full value history, right here. */
type FactSheetProps = { wid: string; citation: AskCitation | null; open: boolean; onClose: () => void };

function FactSheet({ wid, citation, open, onClose }: FactSheetProps) {
  const { data } = useFact(wid, citation?.id ?? null);
  const areaLabel = useAreaLabels(wid);
  return (
    <FactDrawer
      wid={wid}
      fact={data?.fact ?? null}
      entityName={data?.entity.name ?? citation?.label.split(" · ")[0] ?? ""}
      open={open && citation !== null}
      onOpenChange={(next) => (next ? undefined : onClose())}
      areaLabel={areaLabel}
    />
  );
}

type AskAnswerProps = {
  wid: string;
  item: AskItem;
  /** Ask a question now (follow-ups, retry). Disabled while another request is being sent. */
  onAsk: (question: string) => void;
  busy: boolean;
};

/** One question and its answer, or its live progress while the agent works. */
export function AskAnswer({ wid, item, onAsk, busy }: AskAnswerProps) {
  const active = isRunActive(item.status);
  const [traceOpen, setTraceOpen] = useState(false);
  // The cited fact stays set while its drawer animates closed, so the content doesn't flash.
  const [fact, setFact] = useState<AskCitation | null>(null);
  const [factOpen, setFactOpen] = useState(false);
  const openFact = (citation: AskCitation) => {
    setFact(citation);
    setFactOpen(true);
  };
  // Live detail (with steps) while running, or once the user opens the trace.
  const { data: detail } = useAsk(wid, active || traceOpen ? item.id : null);
  const view: AskItem = detail && detail.id === item.id ? detail : item;
  const running = isRunActive(view.status);
  const elapsed = useElapsed(view.started_at ?? view.created_at, running);
  const asker = view.asked_by ? view.asked_by : "You";

  const renderCitation = (n: number, key: string) => (
    <CitationMarker key={key} wid={wid} n={n} citation={view.citations[n - 1]} onOpenFact={openFact} />
  );

  return (
    <article className="space-y-3" aria-labelledby={`q-${view.id}`} aria-busy={running}>
      {/* The question */}
      <div className="flex justify-end">
        <div className="max-w-[min(42rem,100%)] rounded-2xl rounded-br-md bg-primary/10 px-4 py-2.5">
          <p id={`q-${view.id}`} className="text-sm font-medium text-pretty break-words">
            {view.question}
          </p>
          <p className="mt-1 text-right text-xs text-muted-foreground">
            {asker} · <RelativeTime value={view.created_at} />
          </p>
        </div>
      </div>

      {/* The answer */}
      <div className="rounded-2xl rounded-tl-md border bg-card p-4 shadow-xs sm:p-5">
        {running ? (
          <div className="space-y-4" aria-live="polite">
            <div className="flex flex-wrap items-center gap-2 text-sm">
              <Spinner className="size-4 text-brand" aria-hidden="true" />
              <span className="font-medium">{liveLabel(detail?.steps, view.status === "queued")}</span>
              {elapsed !== null ? (
                <span className="metric text-xs text-muted-foreground">{formatDuration(elapsed)}</span>
              ) : null}
            </div>
            {detail?.steps.length ? (
              <RunTrace steps={detail.steps} live className="max-h-[28rem] overflow-y-auto pr-1" />
            ) : (
              <div className="space-y-2" aria-hidden="true">
                <Skeleton className="h-4 w-3/4" />
                <Skeleton className="h-4 w-1/2" />
              </div>
            )}
          </div>
        ) : view.status === "succeeded" && view.answer_markdown ? (
          <div className="space-y-4">
            <AnswerMarkdown markdown={view.answer_markdown} renderCitation={renderCitation} />

            {view.used_web ? (
              <Alert className="border-amber-300 bg-amber-50/70 dark:border-amber-500/30 dark:bg-amber-500/5">
                <Globe aria-hidden="true" className="text-amber-700 dark:text-amber-300" />
                <AlertTitle>Includes web results outside SignalLens memory</AlertTitle>
                <AlertDescription>
                  Points cited with an amber marker come from a web search and have not been verified.
                </AlertDescription>
              </Alert>
            ) : null}

            {view.evidence_note ? (
              <div className="flex gap-2.5 rounded-lg border border-l-4 border-l-brand/60 bg-muted/30 px-3 py-2.5 text-sm">
                <ShieldCheck className="mt-0.5 size-4 shrink-0 text-brand" aria-hidden="true" />
                <p className="text-pretty">
                  <span className="font-medium">Evidence: </span>
                  {view.evidence_note}
                </p>
              </div>
            ) : null}

            {view.citations.length ? (
              <div className="space-y-2">
                <p className="text-xs font-medium tracking-wide text-muted-foreground uppercase">Sources</p>
                <SourceList wid={wid} citations={view.citations} onOpenFact={openFact} />
              </div>
            ) : null}

            {view.follow_up_questions.length ? (
              <div className="space-y-2">
                <p className="text-xs font-medium tracking-wide text-muted-foreground uppercase">Ask next</p>
                <div className="flex flex-wrap gap-1.5">
                  {view.follow_up_questions.map((question) => (
                    <Button
                      key={question}
                      variant="outline"
                      size="sm"
                      disabled={busy}
                      onClick={() => onAsk(question)}
                      className="h-auto max-w-full justify-start py-1.5 text-left whitespace-normal"
                    >
                      <CornerDownRight aria-hidden="true" className="text-muted-foreground" />
                      <span className="min-w-0 text-pretty">{question}</span>
                    </Button>
                  ))}
                </div>
              </div>
            ) : null}
          </div>
        ) : (
          <Alert variant={view.status === "failed" ? "destructive" : "default"}>
            <AlertTriangle aria-hidden="true" />
            <AlertTitle>
              {view.status === "budget_exhausted" ? "Stopped before an answer was ready" : "Couldn't answer this question"}
            </AlertTitle>
            <AlertDescription className="space-y-2">
              <p className="text-pretty">{view.error ?? "The agent finished without an answer."}</p>
              <Button variant="outline" size="sm" disabled={busy} onClick={() => onAsk(view.question)}>
                <RotateCcw aria-hidden="true" />
                Ask again
              </Button>
            </AlertDescription>
          </Alert>
        )}

        {/* How it was answered */}
        {!running ? (
          <Collapsible open={traceOpen} onOpenChange={setTraceOpen} className="mt-4 border-t pt-3">
            <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1">
              <CollapsibleTrigger asChild>
                <Button variant="ghost" size="xs" className="-ml-2 text-muted-foreground data-open:[&_svg]:rotate-180">
                  <ListTree aria-hidden="true" />
                  How it was answered · {plural(view.steps_count, "step")}
                  <ChevronDown className="transition-transform" aria-hidden="true" />
                </Button>
              </CollapsibleTrigger>
              <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                <RunStatusBadge status={view.status} />
                <UsageInline usage={view.usage} className="hidden sm:inline-flex" />
              </div>
            </div>
            <CollapsibleContent className="mt-3 space-y-3">
              {detail ? (
                <RunTrace steps={detail.steps} />
              ) : (
                <div className="space-y-2" aria-busy="true">
                  <Skeleton className="h-10 w-full" />
                  <Skeleton className="h-10 w-full" />
                </div>
              )}
              <UsageInline usage={view.usage} className="sm:hidden" />
              <Button asChild variant="link" size="sm" className="px-0">
                <Link href={routes.run(wid, view.id)}>Open the full run trace</Link>
              </Button>
            </CollapsibleContent>
          </Collapsible>
        ) : null}
      </div>

      <FactSheet wid={wid} citation={fact} open={factOpen} onClose={() => setFactOpen(false)} />
    </article>
  );
}
