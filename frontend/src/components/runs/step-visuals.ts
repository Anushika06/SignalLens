import { Archive, CheckCircle2, FileText, Globe, type LucideIcon, Newspaper, Search } from "lucide-react";

import { STEP_KIND, type Tone } from "@/lib/labels";
import type { RunStep } from "@/lib/types";

export type StepVisual = { icon: LucideIcon; tone: Tone; label: string };

/**
 * Icon and label for a run step. Tool calls are recognised by tool name so the trace reads
 * naturally: a magnifier for searches, a globe for page fetches, a check for validation.
 */
export function stepVisual(step: Pick<RunStep, "kind" | "name">): StepVisual {
  const name = step.name?.toLowerCase() ?? "";
  if (step.kind === "tool_call" && name) {
    if (name.includes("news")) return { icon: Newspaper, tone: "blue", label: "News search" };
    if (name.includes("search")) return { icon: Search, tone: "blue", label: "Web search" };
    if (/valid|verify|robots|check/.test(name)) return { icon: CheckCircle2, tone: "green", label: "Validation" };
    if (/archive|wayback|cdx/.test(name)) return { icon: Archive, tone: "blue", label: "Web archive" };
    if (/fetch|open|browse|page|http|crawl/.test(name)) return { icon: Globe, tone: "blue", label: "Fetch page" };
    if (/extract|parse|read/.test(name)) return { icon: FileText, tone: "blue", label: "Extraction" };
  }
  const meta = STEP_KIND[step.kind];
  return { icon: meta.icon ?? FileText, tone: meta.tone, label: meta.label };
}
