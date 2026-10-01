"use client";

import { useMemo } from "react";

import { humanize } from "@/lib/format";
import { usePolicy } from "@/lib/hooks";

/**
 * Area keys ("pricing") → labels ("Pricing & fees") from the active policy. Facts, sources and
 * filtered changes only carry the key; without a policy the key is humanised instead.
 */
export function useAreaLabels(wid: string): (key: string) => string {
  const { data: policy } = usePolicy(wid);
  return useMemo(() => {
    const labels = new Map<string, string>();
    for (const area of policy?.spec.areas ?? []) labels.set(area.key, area.label);
    for (const area of policy?.areas ?? []) labels.set(area.key, area.label);
    return (key: string) => labels.get(key) ?? humanize(key);
  }, [policy]);
}
