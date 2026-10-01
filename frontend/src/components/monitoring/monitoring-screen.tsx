"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Radar, Rss } from "lucide-react";

import { PageHeader } from "@/components/common/page-header";
import { ListSkeleton, PageSkeleton, TableSkeleton } from "@/components/common/skeletons";
import { EmptyState, ErrorState } from "@/components/common/states";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useFilteredChanges, useLearnedRules, usePolicy, useSources, useWorkspace } from "@/lib/hooks";
import { type MonitoringTab, routes } from "@/lib/routes";

import { AreasTable } from "./areas-table";
import { FilteredChangesPanel } from "./filtered-changes";
import { LearnedRulesPanel } from "./learned-rules";
import { PolicyHeader } from "./policy-header";
import { SourcesPanel } from "./sources-panel";
import { useAreaLabels } from "./use-area-labels";

const TABS: MonitoringTab[] = ["sources", "areas", "rules", "filtered"];

function isTab(value: string | null): value is MonitoringTab {
  return value !== null && (TABS as string[]).includes(value);
}

function Count({ value }: { value: number | undefined }) {
  if (value === undefined) return null;
  return <span className="metric text-xs text-muted-foreground">{value}</span>;
}

/** No approved plan yet: explain what this page will hold and point to the next step. */
function NoActivePolicy({ wid }: { wid: string }) {
  const { data: workspace } = useWorkspace(wid);
  const pendingPlanId = workspace?.pending_policy_id ?? null;
  return (
    <div className="space-y-8">
      <PageHeader title="Monitoring" />
      <EmptyState
        icon={Radar}
        title="No active monitoring plan yet"
        description="Once you approve a monitoring plan, this page shows exactly what SignalLens watches — areas, sources and how often each is checked — plus the rules it learns from your feedback and the changes it chose to ignore."
        action={
          <Button asChild size="sm" variant={pendingPlanId ? "default" : "outline"}>
            <Link href={pendingPlanId ? routes.plan(wid, pendingPlanId) : routes.dashboard(wid)}>
              {pendingPlanId ? "Review the proposed plan" : "Go to the dashboard"}
            </Link>
          </Button>
        }
      />
    </div>
  );
}

/**
 * The active monitoring configuration: sources (with manual checks and pausing), areas,
 * learned rules (with undo) and the log of filtered changes. Tabs are kept in `?tab=`.
 */
export function MonitoringScreen({ wid }: { wid: string }) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const tabParam = searchParams.get("tab");
  const tab: MonitoringTab = isTab(tabParam) ? tabParam : "sources";
  const focusSourceId = searchParams.get("source");
  const highlightEventId = searchParams.get("event");

  const policy = usePolicy(wid);
  const sources = useSources(wid);
  const rules = useLearnedRules(wid);
  const filtered = useFilteredChanges(wid);
  const areaLabel = useAreaLabels(wid);

  function selectTab(next: string) {
    if (!isTab(next)) return;
    // Switching tabs drops one-off focus params (?source=, ?event=).
    router.replace(`${pathname}?tab=${next}`, { scroll: false });
  }

  if (policy.error?.status === 404) return <NoActivePolicy wid={wid} />;
  if (policy.error) {
    return (
      <div className="space-y-8">
        <PageHeader title="Monitoring" />
        <ErrorState error={policy.error} onRetry={() => void policy.mutate()} />
      </div>
    );
  }
  if (!policy.data) return <PageSkeleton />;

  const activeSources = sources.data?.filter((source) => source.active).length;
  const activeRules = rules.data?.filter((rule) => rule.active).length;

  return (
    <div className="space-y-8">
      <PolicyHeader
        policy={policy.data}
        activeSources={activeSources}
        totalSources={sources.data?.length}
        activeRules={activeRules}
      />

      <Tabs value={tab} onValueChange={selectTab} className="gap-5">
        <div className="-mx-4 overflow-x-auto px-4 pb-1 [scrollbar-width:none] sm:mx-0 sm:px-0 [&::-webkit-scrollbar]:hidden">
          <TabsList className="w-max">
            <TabsTrigger value="sources" className="px-2.5">
              Sources <Count value={sources.data?.length} />
            </TabsTrigger>
            <TabsTrigger value="areas" className="px-2.5">
              Areas <Count value={policy.data.areas.length} />
            </TabsTrigger>
            <TabsTrigger value="rules" className="px-2.5">
              Learned rules <Count value={activeRules} />
            </TabsTrigger>
            <TabsTrigger value="filtered" className="px-2.5">
              Filtered changes <Count value={filtered.data?.length} />
            </TabsTrigger>
          </TabsList>
        </div>

        <TabsContent value="sources">
          {sources.error ? (
            <ErrorState error={sources.error} onRetry={() => void sources.mutate()} />
          ) : !sources.data ? (
            <TableSkeleton rows={6} columns={6} />
          ) : sources.data.length === 0 ? (
            <EmptyState
              icon={Rss}
              title="No sources yet"
              description="Sources are created from the plan when it is approved. Each page or news query is checked on its own schedule."
            />
          ) : (
            <SourcesPanel
              key={focusSourceId ?? "none"}
              wid={wid}
              sources={sources.data}
              focusSourceId={focusSourceId}
              areaLabel={areaLabel}
            />
          )}
        </TabsContent>

        <TabsContent value="areas">
          <AreasTable policy={policy.data} />
        </TabsContent>

        <TabsContent value="rules">
          {rules.error ? (
            <ErrorState error={rules.error} onRetry={() => void rules.mutate()} />
          ) : !rules.data ? (
            <ListSkeleton rows={3} />
          ) : (
            <LearnedRulesPanel wid={wid} rules={rules.data} areaLabel={areaLabel} />
          )}
        </TabsContent>

        <TabsContent value="filtered">
          {filtered.error ? (
            <ErrorState error={filtered.error} onRetry={() => void filtered.mutate()} />
          ) : !filtered.data ? (
            <ListSkeleton rows={5} />
          ) : (
            <FilteredChangesPanel
              wid={wid}
              changes={filtered.data}
              highlightId={highlightEventId}
              areaLabel={areaLabel}
            />
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
}
