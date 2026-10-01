"use client";

import { useState } from "react";
import Link from "next/link";
import { ChevronDown, GraduationCap, Undo2 } from "lucide-react";
import { toast } from "sonner";
import { mutate } from "swr";

import { Chip, MetaBadge } from "@/components/common/badges";
import { RelativeTime } from "@/components/common/relative-time";
import { EmptyState, errorMessage } from "@/components/common/states";
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
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { api, paths } from "@/lib/api";
import { formatDate, humanize, plural } from "@/lib/format";
import { revalidate } from "@/lib/hooks";
import { EVENT_TYPE, LEARNED_RULE_KIND } from "@/lib/labels";
import { routes } from "@/lib/routes";
import type { EventType, LearnedRule } from "@/lib/types";

/** Readable value for a scope/effect entry: area labels, event types, enum words. */
function describeValue(key: string, value: string, areaLabel: (key: string) => string) {
  if (key === "area") return areaLabel(value);
  if (key === "event_type" && value in EVENT_TYPE) return EVENT_TYPE[value as EventType];
  // Only humanise enum-like words; leave domains and names untouched.
  return /^[a-z0-9_]+$/.test(value) ? humanize(value) : value;
}

type RuleChipsProps = {
  label: string;
  entries: Record<string, string>;
  areaLabel: (key: string) => string;
};

function RuleChips({ label, entries, areaLabel }: RuleChipsProps) {
  const items = Object.entries(entries);
  if (items.length === 0) return null;
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <span className="text-xs text-muted-foreground">{label}</span>
      {items.map(([key, value]) => (
        <Chip key={key}>
          <span className="text-muted-foreground">{humanize(key)}:</span>
          <span className="font-medium text-foreground">{describeValue(key, value, areaLabel)}</span>
        </Chip>
      ))}
    </div>
  );
}

function UndoRuleButton({ wid, rule }: { wid: string; rule: LearnedRule }) {
  const [pending, setPending] = useState(false);

  async function undo() {
    setPending(true);
    try {
      const updated = await api.learnedRules.revoke(wid, rule.id);
      await mutate<LearnedRule[]>(
        paths.learnedRules(wid),
        (current) => (current ?? []).map((item) => (item.id === updated.id ? updated : item)),
        { revalidate: true },
      );
      // Effective importance and thresholds may change back.
      void revalidate(paths.policy(wid));
      void revalidate(paths.overview(wid));
      toast.success("Rule undone", { description: "SignalLens is back to your plan's setting for this." });
    } catch (error) {
      toast.error("Couldn't undo the rule", { description: errorMessage(error) });
    } finally {
      setPending(false);
    }
  }

  return (
    <AlertDialog>
      <AlertDialogTrigger asChild>
        <Button variant="outline" size="xs" disabled={pending}>
          <Undo2 aria-hidden="true" />
          Undo
        </Button>
      </AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Undo this learned rule?</AlertDialogTitle>
          <AlertDialogDescription>
            “{rule.explanation}” SignalLens will go back to the setting in your approved plan. Future feedback can teach
            it again.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Keep rule</AlertDialogCancel>
          <AlertDialogAction onClick={() => void undo()}>Undo rule</AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}

function RuleCard({ wid, rule, areaLabel }: { wid: string; rule: LearnedRule; areaLabel: (key: string) => string }) {
  return (
    <article className="flex h-full flex-col gap-3 rounded-xl border bg-card p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <MetaBadge meta={LEARNED_RULE_KIND[rule.kind]} tooltip={false} />
        <span className="text-xs text-muted-foreground">
          Learned <RelativeTime value={rule.created_at} />
        </span>
      </div>
      <p className="text-sm leading-relaxed font-medium text-pretty">{rule.explanation}</p>
      <div className="space-y-1.5">
        <RuleChips label="Applies to" entries={rule.scope} areaLabel={areaLabel} />
        <RuleChips label="Effect" entries={rule.effect} areaLabel={areaLabel} />
      </div>
      <div className="mt-auto flex items-center justify-between gap-3 border-t pt-3">
        <span className="metric text-xs text-muted-foreground">
          Based on {plural(rule.evidence_count, "feedback signal")}
        </span>
        <UndoRuleButton wid={wid} rule={rule} />
      </div>
    </article>
  );
}

type LearnedRulesPanelProps = {
  wid: string;
  rules: LearnedRule[];
  areaLabel: (key: string) => string;
};

/** Visible, reversible adjustments SignalLens made from feedback (spec C10). */
export function LearnedRulesPanel({ wid, rules, areaLabel }: LearnedRulesPanelProps) {
  const active = rules
    .filter((rule) => rule.active)
    .sort((a, b) => b.created_at.localeCompare(a.created_at));
  const undone = rules
    .filter((rule) => !rule.active)
    .sort((a, b) => (b.revoked_at ?? "").localeCompare(a.revoked_at ?? ""));

  return (
    <div className="space-y-6">
      <p className="max-w-3xl text-sm text-pretty text-muted-foreground">
        SignalLens adjusts itself from your feedback — every change is visible and reversible. Each rule says, in plain
        words, what changed and why; undo it and the plan&apos;s original setting applies again straight away.
      </p>

      {active.length === 0 ? (
        <EmptyState
          icon={GraduationCap}
          title="No learned rules yet"
          description="When you mark intelligence as not relevant — too minor, not your area, inaccurate — or ask to always hear about something immediately, SignalLens proposes an adjustment and records it here so you can see it and undo it."
          action={
            <Button asChild variant="outline" size="sm">
              <Link href={routes.intel(wid)}>Review intelligence</Link>
            </Button>
          }
        />
      ) : (
        <ul className="grid gap-3 lg:grid-cols-2">
          {active.map((rule) => (
            <li key={rule.id}>
              <RuleCard wid={wid} rule={rule} areaLabel={areaLabel} />
            </li>
          ))}
        </ul>
      )}

      {undone.length > 0 ? (
        <Collapsible>
          <CollapsibleTrigger asChild>
            <Button variant="ghost" size="sm" className="-ml-2 text-muted-foreground data-open:[&_svg]:rotate-180">
              Undone rules <span className="metric">({undone.length})</span>
              <ChevronDown className="transition-transform" aria-hidden="true" />
            </Button>
          </CollapsibleTrigger>
          <CollapsibleContent>
            <ul className="mt-2 divide-y rounded-xl border bg-muted/20">
              {undone.map((rule) => (
                <li key={rule.id} className="space-y-1 px-4 py-3">
                  <p className="text-sm text-pretty text-muted-foreground line-through decoration-muted-foreground/40">
                    {rule.explanation}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {LEARNED_RULE_KIND[rule.kind].label} · learned {formatDate(rule.created_at)}
                    {rule.revoked_at ? ` · undone ${formatDate(rule.revoked_at)}` : ""}
                  </p>
                </li>
              ))}
            </ul>
          </CollapsibleContent>
        </Collapsible>
      ) : null}
    </div>
  );
}
