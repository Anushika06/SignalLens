"use client";

import { useCallback, useState } from "react";
import { RefreshCw } from "lucide-react";
import { toast } from "sonner";
import { mutate } from "swr";

import { WithTooltip } from "@/components/common/badges";
import { errorMessage } from "@/components/common/states";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Spinner } from "@/components/ui/spinner";
import { Switch } from "@/components/ui/switch";
import { api, paths } from "@/lib/api";
import { revalidate } from "@/lib/hooks";
import type { SourcePatch, SourceView } from "@/lib/types";

import { sourceName } from "./source-parts";

/**
 * PATCH a source with an optimistic update of the cached list; rolls back and rethrows if the
 * API refuses, so callers can show the error.
 */
export function useSourceUpdate(wid: string) {
  return useCallback(
    async (sid: string, patch: SourcePatch) => {
      await mutate<SourceView[]>(
        paths.sources(wid),
        async (current) => {
          const updated = await api.sources.update(wid, sid, patch);
          return (current ?? []).map((source) => (source.id === sid ? updated : source));
        },
        {
          optimisticData: (current) =>
            (current ?? []).map((source) => (source.id === sid ? { ...source, ...patch } : source)),
          rollbackOnError: true,
          populateCache: true,
          revalidate: false,
        },
      );
    },
    [wid],
  );
}

type ActiveSwitchProps = {
  wid: string;
  source: SourceView;
  /** Render a visible "Active/Paused" label next to the switch (cards); tables use aria-label only. */
  withLabel?: boolean;
  id?: string;
};

/** Pause or resume checks for one source. */
export function ActiveSwitch({ wid, source, withLabel = false, id }: ActiveSwitchProps) {
  const update = useSourceUpdate(wid);
  const name = sourceName(source);

  async function toggle(active: boolean) {
    try {
      await update(source.id, { active });
      toast.success(active ? "Source resumed" : "Source paused", {
        description: active
          ? `SignalLens will check ${name} again on its schedule.`
          : `SignalLens will stop checking ${name} until you turn it back on.`,
      });
    } catch (error) {
      toast.error("Couldn't update the source", { description: errorMessage(error) });
    }
  }

  const control = (
    <Switch
      id={id}
      checked={source.active}
      onCheckedChange={(checked) => void toggle(checked)}
      aria-label={withLabel ? undefined : `Monitor ${name}`}
    />
  );
  if (!withLabel) return control;
  return (
    <div className="flex items-center gap-2">
      {control}
      <Label htmlFor={id} className="text-sm font-normal">
        {source.active ? "Active" : "Paused"}
      </Label>
    </div>
  );
}

/** Queue an immediate check (POST /sources/{sid}/check) and pick up the result shortly after. */
export function CheckNowButton({ wid, source }: { wid: string; source: SourceView }) {
  const [pending, setPending] = useState(false);
  const name = sourceName(source);

  async function checkNow() {
    setPending(true);
    try {
      await api.sources.checkNow(wid, source.id);
      toast.success("Check queued", {
        description: `${name} will be checked in a few seconds. The result appears under Recent checks.`,
      });
      // The worker needs a moment; refresh the source list and its checks twice.
      for (const delay of [3_000, 8_000]) {
        window.setTimeout(() => void revalidate(paths.sources(wid)), delay);
      }
    } catch (error) {
      toast.error("Couldn't queue the check", { description: errorMessage(error) });
    } finally {
      setPending(false);
    }
  }

  const button = (
    <Button variant="outline" size="xs" onClick={() => void checkNow()} disabled={pending || !source.active}>
      {pending ? <Spinner className="size-3" /> : <RefreshCw aria-hidden="true" />}
      Check now
    </Button>
  );
  if (source.active) return button;
  return (
    <WithTooltip content="Turn this source on to check it.">
      <span tabIndex={0} className="inline-flex rounded-md">
        {button}
      </span>
    </WithTooltip>
  );
}
