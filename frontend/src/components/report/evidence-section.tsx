import { Archive, BadgeCheck, CircleAlert } from "lucide-react";

import { cn } from "@/lib/utils";
import { EvidenceBadge, MetaBadge, ToneBadge, WithTooltip } from "@/components/common/badges";
import { ExternalLink } from "@/components/common/links";
import { Section } from "@/components/common/page-header";
import { RelativeTime } from "@/components/common/relative-time";
import { formatDate, prettyUrl } from "@/lib/format";
import { SOURCE_CLASS, STANCE, TONE_TEXT } from "@/lib/labels";
import type { Evidence, ReportDetail, Stance } from "@/lib/types";

const STANCE_ORDER: Stance[] = ["supports", "contradicts", "context"];

const STANCE_BORDER: Record<Stance, string> = {
  supports: "border-l-emerald-500/70",
  contradicts: "border-l-red-500/70",
  context: "border-l-border",
};

const ADDED_BY: Record<Evidence["added_by"], string> = {
  pipeline: "Found by monitoring",
  agent: "Found by the investigator",
  user: "Added manually",
};

function QuoteCheck({ verified }: { verified: boolean }) {
  return verified ? (
    <WithTooltip content="The quote was found word for word in the page SignalLens fetched.">
      <span className="inline-flex items-center gap-1 text-xs font-medium text-emerald-700 dark:text-emerald-400">
        <BadgeCheck className="size-3.5" aria-hidden="true" />
        Quote verified
      </span>
    </WithTooltip>
  ) : (
    <WithTooltip content="SignalLens couldn't match this quote to the fetched page text. Treat it with caution.">
      <span className="inline-flex items-center gap-1 text-xs text-amber-700 dark:text-amber-400">
        <CircleAlert className="size-3.5" aria-hidden="true" />
        Quote not verified
      </span>
    </WithTooltip>
  );
}

/** One piece of evidence: who said it, how independent they are, and the exact words. */
function EvidenceCard({ evidence }: { evidence: Evidence }) {
  const stance = STANCE[evidence.stance];
  const StanceIcon = stance.icon;
  return (
    <article
      aria-label={`${stance.label}: ${evidence.publisher}`}
      className={cn(
        "rounded-xl border bg-card p-4",
        evidence.stance === "contradicts" && "border-red-200 dark:border-red-500/30",
      )}
    >
      <header className="flex flex-wrap items-start justify-between gap-2">
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          <span className="text-sm font-medium">{evidence.publisher}</span>
          <MetaBadge meta={SOURCE_CLASS[evidence.source_class]} />
          {evidence.is_archive ? (
            <WithTooltip content="Captured from the Internet Archive rather than the live page.">
              <ToneBadge tone="gray" icon={Archive}>
                Web archive
              </ToneBadge>
            </WithTooltip>
          ) : null}
        </div>
        <span className={cn("inline-flex items-center gap-1 text-xs font-medium", TONE_TEXT[stance.tone])}>
          {StanceIcon ? <StanceIcon className="size-3.5" aria-hidden="true" /> : null}
          {stance.label}
        </span>
      </header>

      <blockquote
        className={cn(
          "mt-3 border-l-2 pl-3 text-sm leading-relaxed text-pretty text-foreground/90",
          STANCE_BORDER[evidence.stance],
        )}
      >
        “{evidence.quote}”
      </blockquote>

      <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1.5">
        <QuoteCheck verified={evidence.quote_verified} />
        <ExternalLink href={evidence.url} className="max-w-full text-xs text-muted-foreground hover:text-foreground">
          {evidence.title ?? prettyUrl(evidence.url)}
        </ExternalLink>
      </div>

      <p className="mt-1.5 flex flex-wrap items-center gap-x-1.5 text-xs text-muted-foreground">
        {evidence.published_at ? (
          <>
            <span>
              Published <time dateTime={evidence.published_at}>{formatDate(evidence.published_at)}</time>
            </span>
            <span aria-hidden="true">·</span>
          </>
        ) : null}
        <span>
          Retrieved <RelativeTime value={evidence.retrieved_at} />
        </span>
        <span aria-hidden="true">·</span>
        <span>{ADDED_BY[evidence.added_by]}</span>
      </p>
    </article>
  );
}

/**
 * Every quote behind the card, supporting first. The status itself is computed by fixed rules
 * in code (primary source → Confirmed, ≥2 independent publishers → Corroborated, …).
 */
export function EvidenceSection({ report }: { report: ReportDetail }) {
  // Array.prototype.sort is stable, so the API's order is kept within each stance.
  const items = [...report.evidence].sort(
    (a, b) => STANCE_ORDER.indexOf(a.stance) - STANCE_ORDER.indexOf(b.stance),
  );
  const counts: Record<Stance, number> = { supports: 0, contradicts: 0, context: 0 };
  for (const item of report.evidence) counts[item.stance] += 1;
  const tally = [
    counts.supports ? `${counts.supports} supporting` : null,
    counts.contradicts ? `${counts.contradicts} contradicting` : null,
    counts.context ? `${counts.context} for context` : null,
  ]
    .filter(Boolean)
    .join(" · ");

  return (
    <Section id="evidence" title="Evidence" description={tally || undefined}>
      <div className="space-y-3">
        <div className="flex flex-col gap-2 rounded-lg border bg-muted/40 p-3 sm:flex-row sm:items-center">
          <EvidenceBadge status={report.evidence_status} className="self-start sm:self-auto" />
          <p className="text-sm text-pretty">{report.evidence_summary}</p>
        </div>
        {items.length > 0 ? (
          <ol className="space-y-3" aria-label="Evidence items">
            {items.map((evidence) => (
              <li key={evidence.id}>
                <EvidenceCard evidence={evidence} />
              </li>
            ))}
          </ol>
        ) : (
          <p className="text-sm text-muted-foreground">
            No evidence has been recorded for this change yet, so it stays unverified.
          </p>
        )}
      </div>
    </Section>
  );
}
