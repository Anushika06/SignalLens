import { cn } from "@/lib/utils";

/** A grid of metrics; renders a <dl> so each label/value pair is announced together. */
export function StatGrid({ className, children }: { className?: string; children: React.ReactNode }) {
  return <dl className={cn("grid gap-4", className)}>{children}</dl>;
}

type StatProps = {
  label: React.ReactNode;
  value: React.ReactNode;
  hint?: React.ReactNode;
  className?: string;
  valueClassName?: string;
};

export function Stat({ label, value, hint, className, valueClassName }: StatProps) {
  return (
    <div className={cn("min-w-0 space-y-1", className)}>
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className={cn("metric text-xl font-semibold tracking-tight", valueClassName)}>{value}</dd>
      {hint ? <dd className="text-xs text-muted-foreground">{hint}</dd> : null}
    </div>
  );
}
