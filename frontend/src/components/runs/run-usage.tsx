import { cn } from "@/lib/utils";
import { formatCompact, formatUsd, plural } from "@/lib/format";
import type { Usage } from "@/lib/types";

/** "3 model calls · 9 tool calls · 18.2K tokens · $0.042" */
export function UsageInline({ usage, className }: { usage: Usage; className?: string }) {
  const tokens = usage.input_tokens + usage.output_tokens;
  return (
    <span className={cn("metric inline-flex flex-wrap items-center gap-x-1.5 text-xs text-muted-foreground", className)}>
      <span>{plural(usage.llm_calls, "model call")}</span>
      <span aria-hidden="true">·</span>
      <span>{plural(usage.tool_calls, "tool call")}</span>
      <span aria-hidden="true">·</span>
      <span>{formatCompact(tokens)} tokens</span>
      <span aria-hidden="true">·</span>
      <span>{formatUsd(usage.est_cost_usd)}</span>
    </span>
  );
}
