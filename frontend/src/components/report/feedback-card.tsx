"use client";

import { useId, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Lightbulb, ThumbsDown, ThumbsUp, Undo2 } from "lucide-react";
import { toast } from "sonner";

import { errorMessage } from "@/components/common/states";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Spinner } from "@/components/ui/spinner";
import { Textarea } from "@/components/ui/textarea";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { api, paths } from "@/lib/api";
import { revalidate } from "@/lib/hooks";
import { FEEDBACK_REASON, FEEDBACK_REASON_HINT, FEEDBACK_REASONS_BY_VERDICT, FEEDBACK_VERDICT } from "@/lib/labels";
import { routes } from "@/lib/routes";
import type { FeedbackReason, FeedbackVerdict, LearnedRule, ReportDetail } from "@/lib/types";

type Saved = { verdict: FeedbackVerdict; reason: FeedbackReason };

const VERDICT_ON = {
  relevant:
    "data-[state=on]:border-emerald-300 data-[state=on]:bg-emerald-50 data-[state=on]:text-emerald-800 dark:data-[state=on]:border-emerald-500/40 dark:data-[state=on]:bg-emerald-500/10 dark:data-[state=on]:text-emerald-300",
  not_relevant:
    "data-[state=on]:border-red-300 data-[state=on]:bg-red-50 data-[state=on]:text-red-800 dark:data-[state=on]:border-red-500/40 dark:data-[state=on]:bg-red-500/10 dark:data-[state=on]:text-red-300",
} as const;

function LearnedRulesNote({ wid, rules }: { wid: string; rules: LearnedRule[] }) {
  if (rules.length === 0) return null;
  return (
    <div className="rounded-lg border border-brand/20 bg-brand/5 p-3 text-sm">
      <p className="font-medium">What SignalLens learned</p>
      <ul className="mt-1 space-y-1 text-pretty text-muted-foreground">
        {rules.map((rule) => (
          <li key={rule.id}>{rule.explanation}</li>
        ))}
      </ul>
      <Link
        href={routes.monitoring(wid, "rules")}
        className="mt-2 inline-flex items-center gap-1 text-xs font-medium text-brand underline-offset-4 hover:underline"
      >
        <Undo2 className="size-3.5" aria-hidden="true" />
        Review or undo in Learned rules
      </Link>
    </div>
  );
}

/**
 * Relevant / Not relevant, then a reason. Reasons map to visible, reversible learned rules
 * (e.g. "too minor" raises the alert threshold after repeated signals), so the card says what
 * SignalLens may learn before the user submits and what it did learn afterwards.
 */
export function FeedbackCard({ wid, report }: { wid: string; report: ReportDetail }) {
  const router = useRouter();
  const titleId = useId();
  const reasonLabelId = useId();
  const noteId = useId();

  const [saved, setSaved] = useState<Saved | null>(report.feedback);
  const [editing, setEditing] = useState(!report.feedback);
  const [verdict, setVerdict] = useState<FeedbackVerdict | null>(report.feedback?.verdict ?? null);
  const [reason, setReason] = useState<FeedbackReason | null>(report.feedback?.reason ?? null);
  const [note, setNote] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [learned, setLearned] = useState<LearnedRule[]>([]);

  function chooseVerdict(next: FeedbackVerdict | null) {
    setVerdict(next);
    setError(null);
    // Reasons differ per verdict; keep the current one only if it still applies.
    if (!next || !reason || !FEEDBACK_REASONS_BY_VERDICT[next].includes(reason)) setReason(null);
  }

  function startEditing() {
    setVerdict(saved?.verdict ?? null);
    setReason(saved?.reason ?? null);
    setLearned([]);
    setEditing(true);
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!verdict || !reason) return;
    setSubmitting(true);
    setError(null);
    try {
      const result = await api.reports.feedback(wid, report.id, { verdict, reason, note: note.trim() || undefined });
      setSaved({ verdict, reason });
      setLearned(result.learned_rules);
      setEditing(false);
      setNote("");

      const hasRules = result.learned_rules.length > 0;
      toast.success(result.message, {
        description: hasRules ? (
          <span className="block space-y-1">
            {result.learned_rules.map((rule) => (
              <span key={rule.id} className="block">
                {rule.explanation}
              </span>
            ))}
            <span className="block opacity-80">You can review or undo this in Monitoring → Learned rules.</span>
          </span>
        ) : undefined,
        action: hasRules ? { label: "Review", onClick: () => router.push(routes.monitoring(wid, "rules")) } : undefined,
        duration: hasRules ? 12_000 : 5_000,
      });

      // Lists show feedback state; learned rules can change thresholds and area importance.
      void revalidate(paths.reports(wid));
      void revalidate(paths.learnedRules(wid));
      void revalidate(paths.overview(wid));
      void revalidate(paths.policy(wid));
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSubmitting(false);
    }
  }

  if (!editing && saved) {
    const Icon = saved.verdict === "relevant" ? ThumbsUp : ThumbsDown;
    return (
      <Card size="sm">
        <CardHeader>
          <CardTitle>Your feedback</CardTitle>
          <CardDescription>It tunes what SignalLens alerts you about.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <p className="flex items-center gap-2 text-sm">
            <Icon className="size-4 shrink-0 text-brand" aria-hidden="true" />
            <span>
              <span className="font-medium">{FEEDBACK_VERDICT[saved.verdict]}</span> — {FEEDBACK_REASON[saved.reason]}
            </span>
          </p>
          <LearnedRulesNote wid={wid} rules={learned} />
          <Button variant="outline" size="sm" onClick={startEditing}>
            Change feedback
          </Button>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card size="sm">
      <CardHeader>
        <CardTitle id={titleId}>Is this relevant to you?</CardTitle>
        <CardDescription>
          Your answer tunes future alerts. Anything SignalLens learns from it is shown to you and can be undone.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={submit} className="space-y-4" aria-labelledby={titleId}>
          <ToggleGroup
            type="single"
            variant="outline"
            spacing={2}
            value={verdict ?? ""}
            onValueChange={(value) => chooseVerdict((value || null) as FeedbackVerdict | null)}
            aria-label="Relevance"
            className="grid w-full grid-cols-2"
          >
            <ToggleGroupItem value="relevant" className={`w-full ${VERDICT_ON.relevant}`}>
              <ThumbsUp aria-hidden="true" />
              Relevant
            </ToggleGroupItem>
            <ToggleGroupItem value="not_relevant" className={`w-full ${VERDICT_ON.not_relevant}`}>
              <ThumbsDown aria-hidden="true" />
              Not relevant
            </ToggleGroupItem>
          </ToggleGroup>

          {verdict ? (
            <>
              <div className="space-y-2">
                <p id={reasonLabelId} className="text-xs font-medium text-muted-foreground">
                  {verdict === "relevant" ? "What made it useful?" : "Why not?"}
                </p>
                <ToggleGroup
                  type="single"
                  variant="outline"
                  size="sm"
                  spacing={1.5}
                  value={reason ?? ""}
                  onValueChange={(value) => setReason((value || null) as FeedbackReason | null)}
                  aria-labelledby={reasonLabelId}
                  className="flex w-full flex-wrap"
                >
                  {FEEDBACK_REASONS_BY_VERDICT[verdict].map((key) => (
                    <ToggleGroupItem
                      key={key}
                      value={key}
                      className="rounded-full data-[state=on]:border-brand/40 data-[state=on]:bg-brand/10 data-[state=on]:text-brand"
                    >
                      {FEEDBACK_REASON[key]}
                    </ToggleGroupItem>
                  ))}
                </ToggleGroup>
                {reason && FEEDBACK_REASON_HINT[reason] ? (
                  <p className="flex gap-1.5 text-xs text-pretty text-muted-foreground">
                    <Lightbulb className="mt-0.5 size-3.5 shrink-0 text-brand" aria-hidden="true" />
                    {FEEDBACK_REASON_HINT[reason]}
                  </p>
                ) : null}
              </div>

              <div className="space-y-1.5">
                <Label htmlFor={noteId} className="text-xs font-medium text-muted-foreground">
                  Note (optional)
                </Label>
                <Textarea
                  id={noteId}
                  value={note}
                  onChange={(event) => setNote(event.target.value)}
                  rows={2}
                  maxLength={1000}
                  placeholder={reason === "other" ? "What was off about this card?" : "Anything the agent should know?"}
                />
              </div>
            </>
          ) : null}

          {error ? (
            <p role="alert" className="text-sm text-destructive">
              {error}
            </p>
          ) : null}

          {verdict ? (
            <div className="flex flex-wrap items-center gap-2">
              <Button type="submit" size="sm" disabled={!reason || submitting}>
                {submitting ? <Spinner /> : null}
                Send feedback
              </Button>
              {saved ? (
                <Button type="button" variant="ghost" size="sm" onClick={() => setEditing(false)}>
                  Cancel
                </Button>
              ) : null}
              {!reason ? <span className="text-xs text-muted-foreground">Pick a reason to send.</span> : null}
            </div>
          ) : null}
        </form>
      </CardContent>
    </Card>
  );
}
