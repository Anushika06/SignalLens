"use client";

import { useEffect, useRef, useState } from "react";
import { mutate } from "swr";

import { api, paths } from "@/lib/api";
import type { MonitoringPlan } from "@/lib/types";

export type DraftState = "idle" | "saving" | "saved" | "error";

const DEBOUNCE_MS = 1200;

/**
 * Quietly saves review edits as a draft (PUT /plans/{pid}/spec) a moment after the user stops
 * editing, so leaving the page doesn't lose them. Approval sends the spec regardless, so a
 * failed draft save is only a warning.
 */
export function useDraftAutosave(wid: string, pid: string, spec: MonitoringPlan) {
  const [state, setState] = useState<DraftState>("idle");
  const dirty = useRef(false);
  const paused = useRef(false);

  useEffect(() => {
    if (!dirty.current || paused.current) return;
    const timer = setTimeout(async () => {
      if (paused.current) return;
      setState("saving");
      try {
        const saved = await api.plans.saveSpec(wid, pid, spec);
        // Keep the cached plan in step, so coming back to this page shows the saved draft.
        await mutate(paths.plan(wid, pid), saved, { revalidate: false });
        if (!paused.current) setState("saved");
      } catch {
        if (!paused.current) setState("error");
      }
    }, DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [wid, pid, spec]);

  return {
    state,
    /** Call from edit handlers: the next spec change should be saved. */
    markDirty: () => {
      dirty.current = true;
    },
    /** Stop saving while the plan is being approved or rejected. */
    pause: () => {
      paused.current = true;
    },
    resume: () => {
      paused.current = false;
    },
  };
}
