import type { LucideIcon } from "lucide-react";

import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import {
  EVIDENCE,
  EVIDENCE_EXPLAINER,
  EVIDENCE_ORDER,
  type Meta,
  SEVERITY,
  SEVERITY_EXPLAINER,
  TONE_BADGE,
  TONE_DOT,
  type Tone,
} from "@/lib/labels";
import type { EvidenceStatus, Severity } from "@/lib/types";

type ToneBadgeProps = React.ComponentProps<"span"> & { tone: Tone; icon?: LucideIcon };

/** The one badge shape used across the product: tinted, bordered, always with text. */
export function ToneBadge({ tone, icon: Icon, className, children, ...props }: ToneBadgeProps) {
  return (
    <Badge variant="outline" className={cn("rounded-md font-medium", TONE_BADGE[tone], className)} {...props}>
      {Icon ? <Icon aria-hidden="true" /> : null}
      {children}
    </Badge>
  );
}

type WithTooltipProps = {
  content: React.ReactNode;
  children: React.ReactElement;
  /** Make the trigger reachable by keyboard (use where the explanation matters). */
  focusable?: boolean;
  side?: "top" | "bottom" | "left" | "right";
};

export function WithTooltip({ content, children, focusable = false, side }: WithTooltipProps) {
  if (!content) return children;
  return (
    <Tooltip>
      <TooltipTrigger asChild {...(focusable ? { tabIndex: 0 } : {})}>
        {children}
      </TooltipTrigger>
      <TooltipContent side={side} className="max-w-xs text-pretty">
        {content}
      </TooltipContent>
    </Tooltip>
  );
}

type MetaBadgeProps = {
  meta: Meta;
  /** Tooltip content; defaults to the meta description. Pass `false` for none. */
  tooltip?: React.ReactNode | false;
  showIcon?: boolean;
  focusable?: boolean;
  className?: string;
};

/** Renders any enum value from lib/labels.ts as a badge, with its explanation as a tooltip. */
export function MetaBadge({ meta, tooltip, showIcon = true, focusable, className }: MetaBadgeProps) {
  const badge = (
    <ToneBadge tone={meta.tone} icon={showIcon ? meta.icon : undefined} className={className}>
      {meta.label}
    </ToneBadge>
  );
  const content = tooltip === false ? null : (tooltip ?? meta.description);
  return content ? (
    <WithTooltip content={content} focusable={focusable}>
      {badge}
    </WithTooltip>
  ) : (
    badge
  );
}

// --- Severity: how much it matters to us ------------------------------------------------------

export function SeverityDot({ severity, className }: { severity: Severity; className?: string }) {
  return (
    <span className={cn("inline-flex shrink-0 items-center", className)}>
      <span aria-hidden="true" className={cn("size-2 rounded-full", TONE_DOT[SEVERITY[severity].tone])} />
      <span className="sr-only">{SEVERITY[severity].label} severity</span>
    </span>
  );
}

type SeverityBadgeProps = {
  severity: Severity;
  focusable?: boolean;
  withTooltip?: boolean;
  className?: string;
};

export function SeverityBadge({ severity, focusable, withTooltip = true, className }: SeverityBadgeProps) {
  const meta = SEVERITY[severity];
  const badge = (
    <ToneBadge tone={meta.tone} className={className}>
      <span aria-hidden="true" className={cn("size-1.5 rounded-full", TONE_DOT[meta.tone])} />
      {meta.label}
      <span className="sr-only"> severity</span>
    </ToneBadge>
  );
  if (!withTooltip) return badge;
  return (
    <WithTooltip
      focusable={focusable}
      content={
        <span className="block space-y-1">
          <span className="block font-medium">
            {meta.label} severity — {meta.description}
          </span>
          <span className="block opacity-80">{SEVERITY_EXPLAINER}</span>
        </span>
      }
    >
      {badge}
    </WithTooltip>
  );
}

// --- Evidence status: how sure we are ---------------------------------------------------------

type EvidenceBadgeProps = {
  status: EvidenceStatus;
  /** "rule" explains this status; "all" lists every status rule with this one highlighted. */
  explain?: "rule" | "all" | false;
  focusable?: boolean;
  className?: string;
};

export function EvidenceBadge({ status, explain = "rule", focusable, className }: EvidenceBadgeProps) {
  const meta = EVIDENCE[status];
  const badge = (
    <ToneBadge tone={meta.tone} icon={meta.icon} className={className}>
      {meta.label}
    </ToneBadge>
  );
  if (!explain) return badge;
  const content =
    explain === "all" ? (
      <span className="block space-y-1.5">
        <span className="block opacity-80">{EVIDENCE_EXPLAINER}</span>
        {EVIDENCE_ORDER.map((key) => (
          <span key={key} className={cn("block", key === status ? "font-medium" : "opacity-70")}>
            {key === status ? "▸ " : ""}
            {EVIDENCE[key].label}: {EVIDENCE[key].description}
          </span>
        ))}
      </span>
    ) : (
      <span className="block">
        <span className="font-medium">{meta.label}.</span> {meta.description}
      </span>
    );
  return (
    <WithTooltip content={content} focusable={focusable}>
      {badge}
    </WithTooltip>
  );
}

// --- Small chips ------------------------------------------------------------------------------

export function Chip({ className, children, ...props }: React.ComponentProps<"span">) {
  return (
    <span
      className={cn(
        "inline-flex h-5 max-w-full items-center gap-1 truncate rounded-md border bg-background px-1.5 text-xs text-muted-foreground",
        className,
      )}
      {...props}
    >
      {children}
    </span>
  );
}

/** Monitoring area (e.g. "Pricing & fees"). */
export function AreaChip({ label, className }: { label: string; className?: string }) {
  return <Chip className={className}>{label}</Chip>;
}
