"use client";

import { useSyncExternalStore } from "react";

import { cn } from "@/lib/utils";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { formatDateTime, formatRelative } from "@/lib/format";

// One shared 30-second ticker keeps every relative time on screen fresh.
const listeners = new Set<() => void>();
let tick = 0;
let timer: ReturnType<typeof setInterval> | null = null;

function subscribe(listener: () => void) {
  listeners.add(listener);
  timer ??= setInterval(() => {
    tick += 1;
    listeners.forEach((notify) => notify());
  }, 30_000);
  return () => {
    listeners.delete(listener);
    if (listeners.size === 0 && timer) {
      clearInterval(timer);
      timer = null;
    }
  };
}

/** Re-renders the caller every 30 s (for anything showing "time since"). */
export function useTick() {
  return useSyncExternalStore(
    subscribe,
    () => tick,
    () => 0,
  );
}

type RelativeTimeProps = {
  value: string | null | undefined;
  /** Shown before the relative time, e.g. "Detected ". */
  prefix?: string;
  className?: string;
};

/** "12 min ago", with the absolute local date and time in a tooltip. */
export function RelativeTime({ value, prefix, className }: RelativeTimeProps) {
  useTick();
  if (!value) return <span className={cn("text-muted-foreground", className)}>—</span>;
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <time dateTime={value} className={cn("whitespace-nowrap", className)}>
          {prefix}
          {formatRelative(value)}
        </time>
      </TooltipTrigger>
      <TooltipContent>{formatDateTime(value)}</TooltipContent>
    </Tooltip>
  );
}
