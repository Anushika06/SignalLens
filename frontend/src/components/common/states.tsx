import { AlertTriangle, type LucideIcon, RefreshCw } from "lucide-react";

import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Empty, EmptyContent, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from "@/components/ui/empty";
import { isApiError } from "@/lib/api";

type EmptyStateProps = {
  icon?: LucideIcon;
  title: string;
  /** Explain what will appear here and why it is empty right now. */
  description?: React.ReactNode;
  action?: React.ReactNode;
  className?: string;
};

export function EmptyState({ icon: Icon, title, description, action, className }: EmptyStateProps) {
  return (
    <Empty className={cn("border bg-card/40 py-10", className)}>
      <EmptyHeader>
        {Icon ? (
          <EmptyMedia variant="icon">
            <Icon aria-hidden="true" />
          </EmptyMedia>
        ) : null}
        <EmptyTitle>{title}</EmptyTitle>
        {description ? <EmptyDescription>{description}</EmptyDescription> : null}
      </EmptyHeader>
      {action ? <EmptyContent>{action}</EmptyContent> : null}
    </Empty>
  );
}

export function errorMessage(error: unknown): string {
  if (isApiError(error)) return error.detail;
  if (error instanceof Error) return error.message;
  return "Something unexpected happened.";
}

type ErrorStateProps = {
  error: unknown;
  onRetry?: () => void;
  title?: string;
  className?: string;
};

/** Friendly failure block with a retry button (hidden for 404s, where retrying won't help). */
export function ErrorState({ error, onRetry, title, className }: ErrorStateProps) {
  const status = isApiError(error) ? error.status : undefined;
  const heading =
    title ??
    (status === 404
      ? "Not found"
      : status === 403
        ? "You don't have access to this"
        : status === 0
          ? "Can't reach SignalLens"
          : "Couldn't load this");
  return (
    <div
      role="alert"
      className={cn("flex flex-col items-center gap-3 rounded-xl border border-dashed px-6 py-10 text-center", className)}
    >
      <span className="flex size-9 items-center justify-center rounded-lg bg-destructive/10 text-destructive">
        <AlertTriangle className="size-4" aria-hidden="true" />
      </span>
      <div className="max-w-md space-y-1">
        <p className="text-sm font-medium">{heading}</p>
        <p className="text-sm text-pretty text-muted-foreground">{errorMessage(error)}</p>
      </div>
      {onRetry && status !== 404 ? (
        <Button variant="outline" size="sm" onClick={onRetry}>
          <RefreshCw aria-hidden="true" />
          Try again
        </Button>
      ) : null}
    </div>
  );
}
