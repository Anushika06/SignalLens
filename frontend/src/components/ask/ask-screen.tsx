"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { ArrowUp, MessageSquareText, Sparkles } from "lucide-react";
import { toast } from "sonner";

import { PageHeader } from "@/components/common/page-header";
import { ListSkeleton } from "@/components/common/skeletons";
import { EmptyState, ErrorState, errorMessage } from "@/components/common/states";
import { Button } from "@/components/ui/button";
import { Kbd } from "@/components/ui/kbd";
import { Spinner } from "@/components/ui/spinner";
import { Textarea } from "@/components/ui/textarea";
import { api, paths } from "@/lib/api";
import { revalidate, useAskHistory, useEntities } from "@/lib/hooks";
import type { AskItem, EntitySummary } from "@/lib/types";
import { cn } from "@/lib/utils";

import { AskAnswer } from "./ask-answer";

const MAX_CHARS = 500;

/** Example prompts, filled in with entities this workspace actually monitors. */
function examplePrompts(entities: EntitySummary[] | undefined): string[] {
  const named = (entities ?? []).filter((e) => e.role !== "us" && e.kind !== "regulator");
  const subject = named.find((e) => e.role === "subject") ?? named[0];
  const other = named.find((e) => e !== subject && (e.role === "competitor" || e.role === "subject"));
  const a = subject?.name ?? "our main competitor";
  const poss = (name: string) => (name.endsWith("s") ? `${name}'` : `${name}'s`);
  return [
    `What has ${a} changed in pricing this year?`,
    "Which competitor announced partnerships recently, and is it confirmed?",
    "What should Compliance look at this week?",
    other ? `Compare ${poss(a)} and ${poss(other.name)} current fees` : `What are ${poss(a)} current fees?`,
  ];
}

type ComposerProps = {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  busy: boolean;
  examples: string[];
  onExample: (question: string) => void;
  showExamples: boolean;
  /** With a history to read, examples only take room on wider screens. */
  compactExamples: boolean;
  inputRef: React.RefObject<HTMLTextAreaElement | null>;
};

function Composer({
  value,
  onChange,
  onSubmit,
  busy,
  examples,
  onExample,
  showExamples,
  compactExamples,
  inputRef,
}: ComposerProps) {
  const trimmed = value.trim();
  const tooLong = value.length > MAX_CHARS;
  const canSend = trimmed.length >= 3 && !tooLong && !busy;
  return (
    <div className="space-y-3">
      <form
        onSubmit={(event) => {
          event.preventDefault();
          if (canSend) onSubmit();
        }}
        className="rounded-2xl border bg-card p-2 shadow-xs transition-colors focus-within:border-ring focus-within:ring-3 focus-within:ring-ring/30"
      >
        <label htmlFor="ask-question" className="sr-only">
          Your question
        </label>
        <Textarea
          id="ask-question"
          ref={inputRef}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
              event.preventDefault();
              if (canSend) onSubmit();
            }
          }}
          placeholder="Ask about the companies you monitor — e.g. “What has changed in pricing this month?”"
          rows={2}
          maxLength={MAX_CHARS + 50}
          aria-invalid={tooLong || undefined}
          aria-describedby="ask-hint"
          className="max-h-48 min-h-14 resize-none border-0 bg-transparent px-2 shadow-none focus-visible:ring-0 dark:bg-transparent"
        />
        <div className="flex items-center justify-between gap-2 px-2 pt-1">
          <p id="ask-hint" className="min-w-0 text-xs text-muted-foreground">
            {tooLong ? (
              <span className="text-destructive">Keep it under {MAX_CHARS} characters.</span>
            ) : (
              <>
                <span className="hidden sm:inline">
                  <Kbd>Enter</Kbd> to ask · <Kbd>Shift</Kbd>+<Kbd>Enter</Kbd> for a new line ·{" "}
                </span>
                Answers come from your world state, with sources.
              </>
            )}
          </p>
          <Button type="submit" size="sm" disabled={!canSend} className="shrink-0">
            {busy ? <Spinner aria-hidden="true" /> : <ArrowUp aria-hidden="true" />}
            Ask
          </Button>
        </div>
      </form>
      {showExamples ? (
        <div
          className={cn("flex-wrap gap-1.5", compactExamples ? "hidden sm:flex" : "flex")}
          aria-label="Example questions"
        >
          {examples.map((example) => (
            <Button
              key={example}
              variant="outline"
              size="sm"
              disabled={busy}
              onClick={() => onExample(example)}
              className="h-auto max-w-full rounded-full py-1.5 text-left whitespace-normal"
            >
              <Sparkles aria-hidden="true" className="text-brand" />
              <span className="min-w-0 text-pretty">{example}</span>
            </Button>
          ))}
        </div>
      ) : null}
    </div>
  );
}

/**
 * Ask: natural-language questions over the workspace's memory. The agent searches tracked facts,
 * their history and the intelligence cards, and answers with numbered citations — or says
 * plainly that SignalLens has no data.
 */
export function AskScreen({ wid }: { wid: string }) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const { data: history, error, isLoading, mutate } = useAskHistory(wid);
  const { data: entities } = useEntities(wid);
  const [question, setQuestion] = useState(() => searchParams.get("q") ?? "");
  const [busy, setBusy] = useState(false);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const examples = useMemo(() => examplePrompts(entities), [entities]);

  // A pre-filled question (?q=…) is shown for review, not sent; drop it from the URL.
  useEffect(() => {
    if (searchParams.get("q")) {
      router.replace(pathname, { scroll: false });
      inputRef.current?.focus();
    }
  }, [searchParams, router, pathname]);

  async function ask(text: string) {
    const q = text.trim();
    if (q.length < 3 || busy) return;
    setBusy(true);
    try {
      const started = await api.ask.create(wid, { question: q });
      const placeholder: AskItem = {
        id: started.run_id,
        status: started.status,
        question: q,
        asked_by: null,
        answer_markdown: null,
        citations: [],
        evidence_note: null,
        follow_up_questions: [],
        used_web: false,
        error: null,
        steps_count: 0,
        created_at: new Date().toISOString(),
        started_at: null,
        finished_at: null,
        usage: { llm_calls: 0, tool_calls: 0, input_tokens: 0, output_tokens: 0, est_cost_usd: 0 },
      };
      await mutate((items) => [placeholder, ...(items ?? []).filter((item) => item.id !== placeholder.id)], {
        revalidate: true,
      });
      setQuestion("");
      void revalidate(paths.runs(wid));
      window.scrollTo({ top: 0, behavior: "smooth" });
    } catch (err) {
      toast.error("Couldn't ask SignalLens", { description: errorMessage(err) });
    } finally {
      setBusy(false);
    }
  }

  const items = history ?? [];

  return (
    <div className="mx-auto w-full max-w-3xl space-y-6">
      <PageHeader
        title="Ask SignalLens"
        description="Ask about the companies and topics you monitor. Answers come only from your world state — tracked facts and their history, detected changes and intelligence cards — and every statement cites its source. If SignalLens has no data, it says so."
      />

      <Composer
        value={question}
        onChange={setQuestion}
        onSubmit={() => void ask(question)}
        busy={busy}
        examples={examples}
        onExample={(example) => void ask(example)}
        showExamples={!isLoading}
        compactExamples={items.length > 0}
        inputRef={inputRef}
      />

      <section aria-label="Questions and answers" className="space-y-8">
        {isLoading ? (
          <ListSkeleton rows={3} />
        ) : error ? (
          <ErrorState error={error} onRetry={() => void mutate()} />
        ) : items.length === 0 ? (
          <EmptyState
            icon={MessageSquareText}
            title="No questions yet"
            description="Try one of the examples above. The agent searches SignalLens memory, opens the cards and fact histories it needs, and shows its work as it goes."
          />
        ) : (
          items.map((item) => <AskAnswer key={item.id} wid={wid} item={item} onAsk={(q) => void ask(q)} busy={busy} />)
        )}
      </section>
    </div>
  );
}
