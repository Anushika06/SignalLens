import { AreaChip, Chip, MetaBadge } from "@/components/common/badges";
import { ExternalLink } from "@/components/common/links";
import { Section } from "@/components/common/page-header";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { CHECK_INTERVAL_OPTIONS, formatInterval, prettyUrl } from "@/lib/format";
import { AUTHORITY, PRIORITY, PRIORITY_ORDER, SOURCE_KIND } from "@/lib/labels";
import type { MonitoringPlan, PlanSource, Priority } from "@/lib/types";

import { indexSpec, type SpecIndex, sourceSkipReason } from "./plan-spec";
import { ControlLabel, ReviewItem, WhyLine } from "./review-item";
import { SourceValidationLine } from "./source-validation";

type SourcesSectionProps = {
  spec: MonitoringPlan;
  onChange: (ref: string, patch: Partial<PlanSource>) => void;
};

function intervalOptions(current: number): number[] {
  const options: number[] = [...CHECK_INTERVAL_OPTIONS];
  return options.includes(current) ? options : [...options, current].sort((a, b) => a - b);
}

function SourceTitle({ source }: { source: PlanSource }) {
  const Icon = SOURCE_KIND[source.kind].icon;
  return (
    <span className="inline-flex max-w-full min-w-0 items-center gap-1.5">
      {Icon ? <Icon className="size-4 shrink-0 text-muted-foreground" aria-hidden="true" /> : null}
      {source.kind === "page" ? (
        <ExternalLink href={source.url} className="max-w-full min-w-0 font-semibold">
          {prettyUrl(source.url) || source.ref}
        </ExternalLink>
      ) : (
        <span className="min-w-0 break-words">
          <span className="sr-only">News search for </span>“{source.query ?? source.ref}”
        </span>
      )}
    </span>
  );
}

function SourceItem({
  source,
  index,
  onChange,
}: {
  source: PlanSource;
  index: SpecIndex;
  onChange: SourcesSectionProps["onChange"];
}) {
  const id = (name: string) => `source-${source.ref}-${name}`;
  const name = source.kind === "page" ? prettyUrl(source.url) || source.ref : `news about “${source.query}”`;

  return (
    <ReviewItem
      level={4}
      title={<SourceTitle source={source} />}
      badges={
        <>
          <MetaBadge meta={AUTHORITY[source.authority]} />
          <Chip className="text-foreground">{index.entityName(source.entity_ref)}</Chip>
          {source.areas.map((area) => (
            <AreaChip key={area} label={index.areaLabel(area)} />
          ))}
        </>
      }
      enabled={source.enabled}
      onEnabledChange={(enabled) => onChange(source.ref, { enabled })}
      switchLabel={`Monitor ${name}`}
      skippedBecause={sourceSkipReason(source, index)}
      controls={
        <>
          <div className="space-y-1.5">
            <ControlLabel htmlFor={id("interval")}>Check</ControlLabel>
            <Select
              value={String(source.check_every_hours)}
              onValueChange={(value) => onChange(source.ref, { check_every_hours: Number(value) })}
            >
              <SelectTrigger id={id("interval")} size="sm" className="w-36">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {intervalOptions(source.check_every_hours).map((hours) => (
                  <SelectItem key={hours} value={String(hours)}>
                    {formatInterval(hours)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <ControlLabel htmlFor={id("priority")}>Priority</ControlLabel>
            <Select
              value={source.priority}
              onValueChange={(value) => onChange(source.ref, { priority: value as Priority })}
            >
              <SelectTrigger id={id("priority")} size="sm" className="w-28">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {PRIORITY_ORDER.map((priority) => (
                  <SelectItem key={priority} value={priority}>
                    {PRIORITY[priority].label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          {source.kind === "page" ? (
            <div className="flex min-w-0 max-w-xs items-start gap-2 pb-0.5">
              <Switch
                id={id("backfill")}
                size="sm"
                className="mt-0.5"
                checked={source.backfill}
                onCheckedChange={(backfill) => onChange(source.ref, { backfill })}
                aria-describedby={id("backfill-hint")}
              />
              <div className="min-w-0">
                <label htmlFor={id("backfill")} className="block text-xs font-medium">
                  Replay history
                </label>
                <p id={id("backfill-hint")} className="text-xs text-pretty text-muted-foreground">
                  Replay ~12 months of web-archive history at baseline.
                </p>
              </div>
            </div>
          ) : null}
        </>
      }
    >
      <WhyLine reason={source.reason} />
      <SourceValidationLine validation={source.validation} kind={source.kind} />
    </ReviewItem>
  );
}

/** Pages SignalLens snapshots and diffs, and news queries it watches for new items. */
export function SourcesSection({ spec, onChange }: SourcesSectionProps) {
  const index = indexSpec(spec);
  const groups = [
    {
      key: "page",
      title: "Pages to snapshot",
      hint: "Compared on every check; tracked values are read from these.",
      items: spec.sources.filter((source) => source.kind === "page"),
    },
    {
      key: "news",
      title: "News to watch",
      hint: "New articles become events; many outlets reporting the same thing become corroboration.",
      items: spec.sources.filter((source) => source.kind === "news"),
    },
  ].filter((group) => group.items.length > 0);

  return (
    <Section
      id="sources"
      title={`Sources · ${spec.sources.length}`}
      description="Each source shows why it was chosen and the result of a live check. SignalLens honours robots.txt and never bypasses logins or paywalls."
    >
      {spec.sources.length === 0 ? (
        <p className="text-sm text-muted-foreground">The planner didn&apos;t propose any sources.</p>
      ) : (
        <div className="space-y-5">
          {groups.map((group) => (
            <div key={group.key} className="space-y-2">
              <div>
                <h3 className="text-xs font-medium tracking-wide text-muted-foreground uppercase">{group.title}</h3>
                <p className="text-xs text-muted-foreground">{group.hint}</p>
              </div>
              <ul className="space-y-2">
                {group.items.map((source) => (
                  <SourceItem key={source.ref} source={source} index={index} onChange={onChange} />
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}
    </Section>
  );
}
