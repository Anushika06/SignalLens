import { Chip, MetaBadge } from "@/components/common/badges";
import { PageHeader, TextBlock } from "@/components/common/page-header";
import { RelativeTime } from "@/components/common/relative-time";
import { Stat, StatGrid } from "@/components/common/stat";
import { formatNumber } from "@/lib/format";
import { POLICY_STATUS } from "@/lib/labels";
import type { PolicyView } from "@/lib/types";

type PolicyHeaderProps = {
  policy: PolicyView;
  /** Undefined while sources or rules are still loading. */
  activeSources?: number;
  totalSources?: number;
  activeRules?: number;
};

/** The approved plan in one card: the user's own words, the planner's summary, headline counts. */
export function PolicyHeader({ policy, activeSources, totalSources, activeRules }: PolicyHeaderProps) {
  const { domain } = policy.spec;
  const domainChips = [domain.industry, domain.sector, ...domain.geographies].filter(Boolean);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Monitoring"
        description="What SignalLens watches, how often it checks, what it has learned from your feedback, and what it chose to ignore."
      />
      <section aria-label="Active monitoring plan" className="rounded-xl border bg-card">
        <div className="grid gap-6 p-4 sm:p-5 lg:grid-cols-[minmax(0,1fr)_auto]">
          <div className="min-w-0 space-y-3">
            <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
              <span className="font-medium text-foreground">Plan v{policy.version}</span>
              <MetaBadge meta={POLICY_STATUS[policy.status]} tooltip={false} />
              {policy.approved_at ? (
                <span>
                  Approved <RelativeTime value={policy.approved_at} />
                </span>
              ) : null}
            </div>
            <blockquote className="border-l-2 border-brand pl-3 text-base font-medium text-pretty">
              “{policy.request_text}”
            </blockquote>
            {policy.summary ? <TextBlock text={policy.summary} className="text-muted-foreground" /> : null}
            {domainChips.length > 0 ? (
              <div className="flex flex-wrap gap-1.5">
                {domainChips.map((chip) => (
                  <Chip key={chip}>{chip}</Chip>
                ))}
              </div>
            ) : null}
          </div>
          <StatGrid className="grid-cols-3 gap-6 border-t pt-4 lg:grid-cols-1 lg:content-start lg:gap-4 lg:border-t-0 lg:border-l lg:pt-0 lg:pl-6">
            <Stat label="Areas" value={formatNumber(policy.areas.length)} />
            <Stat
              label="Active sources"
              value={
                activeSources === undefined || totalSources === undefined ? (
                  "—"
                ) : (
                  <>
                    {formatNumber(activeSources)}
                    <span className="text-sm font-normal text-muted-foreground"> / {formatNumber(totalSources)}</span>
                  </>
                )
              }
            />
            <Stat label="Learned rules" value={activeRules === undefined ? "—" : formatNumber(activeRules)} />
          </StatGrid>
        </div>
      </section>
    </div>
  );
}
