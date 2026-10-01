"use client";

import { useEffect, useState } from "react";

/**
 * Milliseconds elapsed since `since`, re-rendering every second while `running` — an honest
 * "how long has this taken" counter instead of a made-up progress percentage.
 */
export function useElapsed(since: string | null | undefined, running: boolean): number | null {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (!running) return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [running]);

  if (!since) return null;
  const start = Date.parse(since);
  return Number.isNaN(start) ? null : Math.max(0, now - start);
}
