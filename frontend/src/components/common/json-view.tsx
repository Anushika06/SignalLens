"use client";

import { useMemo } from "react";

import { cn } from "@/lib/utils";

// Strings (optionally followed by a colon → object keys), literals and numbers.
const TOKEN = /("(?:\\.|[^"\\])*")(\s*:)?|\b(true|false|null)\b|(-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)/g;

function stringify(value: unknown): { text: string; isJson: boolean } {
  if (value === undefined) return { text: "—", isJson: false };
  if (typeof value === "string") return { text: value, isJson: false };
  try {
    return { text: JSON.stringify(value, null, 2), isJson: true };
  } catch {
    return { text: String(value), isJson: false };
  }
}

/** Splits JSON text into coloured spans. Pure text → React nodes; no HTML is injected. */
function highlight(text: string): React.ReactNode[] {
  const nodes: React.ReactNode[] = [];
  let last = 0;
  for (const match of text.matchAll(TOKEN)) {
    const index = match.index ?? 0;
    if (index > last) nodes.push(text.slice(last, index));
    const [token, str, colon, literal, num] = match;
    if (str !== undefined) {
      nodes.push(
        <span key={index} className={colon ? "text-sky-700 dark:text-sky-300" : "text-emerald-700 dark:text-emerald-300"}>
          {str}
        </span>,
      );
      if (colon) nodes.push(colon);
    } else if (literal !== undefined) {
      nodes.push(
        <span key={index} className="text-violet-700 dark:text-violet-300">
          {literal}
        </span>,
      );
    } else if (num !== undefined) {
      nodes.push(
        <span key={index} className="text-amber-700 dark:text-amber-300">
          {num}
        </span>,
      );
    } else {
      nodes.push(token);
    }
    last = index + token.length;
  }
  if (last < text.length) nodes.push(text.slice(last));
  return nodes;
}

type JsonViewProps = {
  value: unknown;
  className?: string;
  /** Pixels before the block scrolls. */
  maxHeight?: number;
  label?: string;
};

/** Pretty, read-only JSON (step inputs/outputs, approval payloads, run results). */
export function JsonView({ value, className, maxHeight = 360, label }: JsonViewProps) {
  const { text, isJson } = useMemo(() => stringify(value), [value]);
  const content = useMemo(() => (isJson ? highlight(text) : text), [isJson, text]);
  return (
    <pre
      aria-label={label}
      tabIndex={0}
      className={cn(
        "overflow-auto rounded-lg border bg-muted/40 p-3 font-mono text-xs leading-relaxed break-words whitespace-pre-wrap text-foreground/90",
        className,
      )}
      style={{ maxHeight }}
    >
      {content}
    </pre>
  );
}
