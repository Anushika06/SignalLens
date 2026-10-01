"use client";

import { useCallback, useMemo } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

import { EVIDENCE_ORDER, SEVERITY_ORDER } from "@/lib/labels";
import type { FeedView, IntelQuery } from "@/lib/routes";
import type { HistoricalFilter, ReportsQuery } from "@/lib/types";

/** Feed filters as they appear in the URL (see `routes.intel`). `view` defaults to live. */
export type FeedFilters = Omit<IntelQuery, "view"> & { view: FeedView };

type FilterKey = "severity" | "area" | "entity" | "evidence";

const VIEWS: readonly FeedView[] = ["live", "historical", "all"];
const FILTER_KEYS: readonly FilterKey[] = ["severity", "area", "entity", "evidence"];

function pick<T extends string>(value: string | null, allowed: readonly T[]): T | undefined {
  return value !== null && (allowed as readonly string[]).includes(value) ? (value as T) : undefined;
}

/**
 * Reads and writes the feed filters in the query string, so a filtered feed can be linked to,
 * bookmarked, and survives a reload. Unknown values are ignored rather than sent to the API.
 */
export function useFeedFilters() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const filters = useMemo<FeedFilters>(
    () => ({
      view: pick(searchParams.get("view"), VIEWS) ?? "live",
      severity: pick(searchParams.get("severity"), SEVERITY_ORDER),
      area: searchParams.get("area") || undefined,
      entity: searchParams.get("entity") || undefined,
      evidence: pick(searchParams.get("evidence"), EVIDENCE_ORDER),
    }),
    [searchParams],
  );

  const update = useCallback(
    (changes: Partial<Record<keyof FeedFilters, string | undefined>>) => {
      const next = new URLSearchParams(searchParams.toString());
      for (const [key, value] of Object.entries(changes)) {
        // "live" is the default view, so it is left out of the URL.
        if (!value || (key === "view" && value === "live")) next.delete(key);
        else next.set(key, value);
      }
      const qs = next.toString();
      router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
    },
    [pathname, router, searchParams],
  );

  const clear = useCallback(
    () => update({ severity: undefined, area: undefined, entity: undefined, evidence: undefined }),
    [update],
  );

  const hasFilters = FILTER_KEYS.some((key) => filters[key] !== undefined);

  return { filters, update, clear, hasFilters };
}

/** Maps URL filters to the GET /reports query (contract §7). */
export function toReportsQuery(filters: FeedFilters): Omit<ReportsQuery, "before" | "limit"> {
  const historical: HistoricalFilter =
    filters.view === "historical" ? "true" : filters.view === "all" ? "all" : "false";
  return {
    historical,
    severity: filters.severity,
    area: filters.area,
    entity_id: filters.entity,
    evidence_status: filters.evidence,
  };
}
