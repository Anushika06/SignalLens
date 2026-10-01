import { Ban } from "lucide-react";

import { cn } from "@/lib/utils";
import { Switch } from "@/components/ui/switch";

type ReviewItemProps = {
  /** Heading content (a name, a URL…). */
  title: React.ReactNode;
  badges?: React.ReactNode;
  enabled: boolean;
  onEnabledChange: (enabled: boolean) => void;
  /** Accessible name of the switch, e.g. "Monitor Razorpay". */
  switchLabel: string;
  /** Set when the item is on but will be skipped because its entity or area is off. */
  skippedBecause?: string | null;
  /** Descriptive content: description, reason, validation… */
  children?: React.ReactNode;
  /** Editable settings shown under the details (disabled while the item is off). */
  controls?: React.ReactNode;
  /** Heading level of the item title (4 when the section has sub-groups). */
  level?: 3 | 4;
  className?: string;
};

/**
 * One reviewable line of the plan with its on/off switch. Off (or skipped) items stay visible
 * but dimmed, with the reason in words — turning something off is always reversible.
 */
export function ReviewItem({
  title,
  badges,
  enabled,
  onEnabledChange,
  switchLabel,
  skippedBecause,
  children,
  controls,
  level = 3,
  className,
}: ReviewItemProps) {
  const Heading = level === 3 ? "h3" : "h4";
  const inactive = !enabled || Boolean(skippedBecause);
  return (
    <li className={cn("rounded-xl border bg-card p-4 transition-colors", inactive && "bg-muted/30", className)}>
      <div className="flex items-start gap-3">
        <div className={cn("min-w-0 flex-1 space-y-2", inactive && "opacity-60")}>
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1.5">
            <Heading className="max-w-full min-w-0 text-sm font-semibold break-words">{title}</Heading>
            {badges}
          </div>
          {children}
        </div>
        <label className="flex shrink-0 cursor-pointer items-center gap-2 pt-0.5">
          <span className="w-6 text-right text-xs text-muted-foreground" aria-hidden="true">
            {enabled ? "On" : "Off"}
          </span>
          <Switch checked={enabled} onCheckedChange={onEnabledChange} aria-label={switchLabel} />
        </label>
      </div>
      {enabled && skippedBecause ? (
        <p className="mt-3 flex items-center gap-1.5 text-xs font-medium text-amber-700 dark:text-amber-300">
          <Ban className="size-3.5 shrink-0" aria-hidden="true" />
          Will be skipped: {skippedBecause}.
        </p>
      ) : null}
      {controls ? (
        <div className={cn("mt-3 border-t pt-3", inactive && "opacity-60")}>
          <fieldset disabled={inactive} className="flex min-w-0 flex-wrap items-end gap-x-5 gap-y-3">
            <legend className="sr-only">Settings</legend>
            {controls}
          </fieldset>
        </div>
      ) : null}
    </li>
  );
}

/** "Why: …" — the planner's reason for proposing an item. */
export function WhyLine({ reason }: { reason: string }) {
  if (!reason) return null;
  return (
    <p className="text-xs text-pretty text-muted-foreground">
      <span className="font-medium text-foreground/70">Why: </span>
      {reason}
    </p>
  );
}

/** Small label above a control inside a review item. */
export function ControlLabel({ htmlFor, children }: { htmlFor: string; children: React.ReactNode }) {
  return (
    <label htmlFor={htmlFor} className="block text-xs font-medium text-muted-foreground">
      {children}
    </label>
  );
}
