import { AlertTriangle, CheckCircle2, CircleDashed } from "lucide-react";

import type { SourceKind, SourceValidation } from "@/lib/types";

function problems(validation: SourceValidation): string[] {
  const found: string[] = [];
  if (validation.http_status !== null && validation.http_status >= 400) found.push(`HTTP ${validation.http_status}`);
  if (validation.robots_allowed === false) found.push("robots.txt disallows fetching it");
  if (validation.quality === "blocked") found.push("access was blocked");
  if (validation.quality === "degenerate") found.push("it looked empty or like an error page");
  if (!validation.ok && found.length === 0) found.push("the check did not pass");
  return found;
}

/**
 * The planner's live check of a proposed source (spec C17): reachable, allowed by robots.txt,
 * with extractable content. ✓ when it passed, ⚠ with the reason when it didn't.
 */
export function SourceValidationLine({ validation, kind }: { validation: SourceValidation | null; kind: SourceKind }) {
  if (!validation) {
    return (
      <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
        <CircleDashed className="size-3.5 shrink-0" aria-hidden="true" />
        Not validated yet
      </p>
    );
  }

  const issues = problems(validation);
  if (issues.length === 0) {
    const facts = [
      validation.http_status !== null ? `HTTP ${validation.http_status}` : null,
      kind === "page" && validation.robots_allowed ? "allowed by robots.txt" : null,
      validation.quality === "ok" ? "content readable" : null,
      validation.title ? `“${validation.title}”` : null,
      validation.note,
    ].filter(Boolean);
    return (
      <p className="flex items-start gap-1.5 text-xs">
        <CheckCircle2 className="mt-px size-3.5 shrink-0 text-emerald-600 dark:text-emerald-400" aria-hidden="true" />
        <span className="min-w-0 break-words">
          <span className="font-medium text-emerald-700 dark:text-emerald-300">Validated</span>
          {facts.length > 0 ? <span className="text-muted-foreground"> · {facts.join(" · ")}</span> : null}
        </span>
      </p>
    );
  }

  return (
    <p className="flex items-start gap-1.5 text-xs">
      <AlertTriangle className="mt-px size-3.5 shrink-0 text-amber-600 dark:text-amber-400" aria-hidden="true" />
      <span className="min-w-0 break-words">
        <span className="font-medium text-amber-700 dark:text-amber-300">Needs a look</span>
        <span className="text-muted-foreground"> · {[...issues, validation.note].filter(Boolean).join(" · ")}</span>
      </span>
    </p>
  );
}
