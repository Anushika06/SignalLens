"use client";

import Link from "next/link";
import { Building2, Globe, History, Lightbulb, type LucideIcon, Zap } from "lucide-react";

import { WithTooltip } from "@/components/common/badges";
import { safeHref } from "@/components/common/links";
import { routes } from "@/lib/routes";
import type { AskCitation, AskCitationKind } from "@/lib/types";
import { cn } from "@/lib/utils";

export const CITATION_KIND: Record<AskCitationKind, { label: string; icon: LucideIcon }> = {
  fact: { label: "Tracked fact", icon: History },
  card: { label: "Intelligence card", icon: Lightbulb },
  event: { label: "Detected change", icon: Zap },
  entity: { label: "Entity", icon: Building2 },
  web: { label: "Web — outside SignalLens memory, not verified", icon: Globe },
};

/** In-app destination of a citation. Facts open their history drawer instead (null here). */
export function citationHref(wid: string, c: AskCitation): string | null {
  switch (c.kind) {
    case "card":
      return routes.report(wid, c.id);
    case "entity":
      return routes.entity(wid, c.id);
    case "event":
      if (c.report_id) return routes.report(wid, c.report_id);
      return c.entity_id ? routes.entity(wid, c.entity_id) : routes.filteredEvent(wid, c.id);
    case "web":
      return safeHref(c.url ?? c.id);
    case "fact":
      return null;
  }
}

type CitationTargetProps = Omit<React.HTMLAttributes<HTMLElement>, "children"> & {
  wid: string;
  citation: AskCitation;
  onOpenFact: (citation: AskCitation) => void;
  children: React.ReactNode;
  /** Forwarded by tooltip triggers (React 19 passes refs as props). */
  ref?: React.Ref<HTMLElement>;
};

/** A link (card, entity, event), an external link (web) or a button that opens a fact's history. */
function CitationTarget({ wid, citation, onOpenFact, children, ref, ...rest }: CitationTargetProps) {
  if (citation.kind === "fact") {
    return (
      <button
        type="button"
        {...rest}
        ref={ref as React.Ref<HTMLButtonElement>}
        onClick={(event) => {
          rest.onClick?.(event);
          onOpenFact(citation);
        }}
      >
        {children}
      </button>
    );
  }
  const href = citationHref(wid, citation);
  if (!href) {
    return (
      <span {...rest} ref={ref as React.Ref<HTMLSpanElement>}>
        {children}
      </span>
    );
  }
  if (citation.kind === "web") {
    return (
      <a {...rest} ref={ref as React.Ref<HTMLAnchorElement>} href={href} target="_blank" rel="noopener noreferrer nofollow">
        {children}
      </a>
    );
  }
  return (
    <Link {...rest} ref={ref as React.Ref<HTMLAnchorElement>} href={href}>
      {children}
    </Link>
  );
}

type MarkerProps = {
  wid: string;
  n: number;
  citation: AskCitation | undefined;
  onOpenFact: (citation: AskCitation) => void;
};

/** Superscript [n] in the answer text, pointing at source n. */
export function CitationMarker({ wid, n, citation, onOpenFact }: MarkerProps) {
  if (!citation) return null; // a marker the server dropped with its invalid citation
  const web = citation.kind === "web";
  return (
    <WithTooltip content={`${CITATION_KIND[citation.kind].label}: ${citation.label}`}>
      <CitationTarget
        wid={wid}
        citation={citation}
        onOpenFact={onOpenFact}
        aria-label={`Source ${n}: ${citation.label}`}
        className={cn(
          "metric mx-0.5 inline-flex h-4 min-w-4 -translate-y-1 items-center justify-center rounded px-1 align-baseline text-[10px] leading-none font-semibold transition-colors focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none",
          web
            ? "bg-amber-100 text-amber-900 hover:bg-amber-200 dark:bg-amber-500/15 dark:text-amber-200 dark:hover:bg-amber-500/25"
            : "bg-primary/10 text-brand hover:bg-primary/20",
        )}
      >
        {n}
      </CitationTarget>
    </WithTooltip>
  );
}

type SourceListProps = {
  wid: string;
  citations: AskCitation[];
  onOpenFact: (citation: AskCitation) => void;
};

/** The numbered sources under an answer, as chips. */
export function SourceList({ wid, citations, onOpenFact }: SourceListProps) {
  if (!citations.length) return null;
  return (
    <ol className="flex flex-wrap gap-1.5" aria-label="Sources">
      {citations.map((citation, index) => {
        const kind = CITATION_KIND[citation.kind];
        const Icon = kind.icon;
        const web = citation.kind === "web";
        return (
          <li key={`${citation.kind}:${citation.id}`} className="max-w-full min-w-0">
            <CitationTarget
              wid={wid}
              citation={citation}
              onOpenFact={onOpenFact}
              aria-label={`Source ${index + 1}, ${kind.label}: ${citation.label}`}
              className={cn(
                "group inline-flex max-w-full min-w-0 items-center gap-1.5 rounded-md border bg-background py-1 pr-2 pl-1 text-left text-xs transition-colors hover:border-brand/40 hover:bg-muted/60 focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none",
                web && "border-amber-300 border-dashed dark:border-amber-500/40",
              )}
            >
              <span
                className={cn(
                  "metric flex size-4 shrink-0 items-center justify-center rounded text-[10px] font-semibold",
                  web ? "bg-amber-100 text-amber-900 dark:bg-amber-500/15 dark:text-amber-200" : "bg-primary/10 text-brand",
                )}
              >
                {index + 1}
              </span>
              <Icon className="size-3.5 shrink-0 text-muted-foreground" aria-hidden="true" />
              <span className="min-w-0 truncate">{citation.label}</span>
              {web ? (
                <span className="shrink-0 text-[10px] font-medium text-amber-700 uppercase dark:text-amber-300">
                  not verified
                </span>
              ) : null}
            </CitationTarget>
          </li>
        );
      })}
    </ol>
  );
}
