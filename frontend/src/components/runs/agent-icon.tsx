import { Bot } from "lucide-react";

import { cn } from "@/lib/utils";
import { AGENT } from "@/lib/labels";
import type { AgentName } from "@/lib/types";

/** The agent's icon in a small tile (planner, investigator, impact analyst…). */
export function AgentIcon({ agent, className }: { agent: AgentName; className?: string }) {
  const Icon = AGENT[agent]?.icon ?? Bot;
  return (
    <span
      aria-hidden="true"
      className={cn(
        "flex size-8 shrink-0 items-center justify-center rounded-lg border bg-muted/60 text-muted-foreground",
        className,
      )}
    >
      <Icon className="size-4" />
    </span>
  );
}

export function isAgentName(value: string | null | undefined): value is AgentName {
  return typeof value === "string" && (Object.keys(AGENT) as string[]).includes(value);
}
