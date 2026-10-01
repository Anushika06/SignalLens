"use client";

import { useState } from "react";
import { KeyRound, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useSystemConfig } from "@/lib/hooks";

const DISMISS_KEY = "signallens:config-banner-dismissed";

function readDismissed() {
  try {
    return typeof window !== "undefined" && window.sessionStorage.getItem(DISMISS_KEY) === "1";
  } catch {
    return false;
  }
}

/** Shown when the backend has no LLM or search provider configured (contract §3). */
export function ConfigBanner() {
  const { data: config } = useSystemConfig();
  const [dismissed, setDismissed] = useState(readDismissed);

  if (!config || dismissed) return null;
  const missing = [
    !config.llm.configured ? "a language model provider" : null,
    !config.search.configured ? "a search provider" : null,
  ].filter(Boolean);
  if (missing.length === 0) return null;

  function dismiss() {
    setDismissed(true);
    try {
      window.sessionStorage.setItem(DISMISS_KEY, "1");
    } catch {
      // Storage unavailable (private mode) — dismissing for this page view is enough.
    }
  }

  return (
    <div
      role="status"
      className="flex items-start gap-3 border-b border-amber-200 bg-amber-50 px-4 py-2.5 text-sm text-amber-900 sm:px-6 dark:border-amber-500/20 dark:bg-amber-500/10 dark:text-amber-200"
    >
      <KeyRound className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
      <p className="min-w-0 flex-1 text-pretty">
        <span className="font-medium">API keys not configured.</span> Add API keys in{" "}
        <code className="rounded bg-amber-100 px-1 font-mono text-xs dark:bg-amber-500/20">backend/.env</code> to
        enable live research — SignalLens needs {missing.join(" and ")}.
      </p>
      <Button
        variant="ghost"
        size="icon-xs"
        onClick={dismiss}
        aria-label="Dismiss"
        className="text-current hover:bg-amber-100 dark:hover:bg-amber-500/20"
      >
        <X aria-hidden="true" />
      </Button>
    </div>
  );
}
