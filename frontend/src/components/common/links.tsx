import Link from "next/link";
import { ExternalLink as ExternalLinkIcon } from "lucide-react";

import { cn } from "@/lib/utils";
import { prettyUrl } from "@/lib/format";
import { routes } from "@/lib/routes";
import type { EntityRef } from "@/lib/types";

/**
 * Only http(s) URLs become links. URLs come from fetched web content, so anything else
 * (javascript:, data:, sandbox://…) is rendered as plain text.
 */
export function safeHref(url: string | null | undefined): string | null {
  if (!url) return null;
  try {
    const parsed = new URL(url);
    return parsed.protocol === "http:" || parsed.protocol === "https:" ? parsed.toString() : null;
  } catch {
    return null;
  }
}

type ExternalLinkProps = {
  href: string | null | undefined;
  children?: React.ReactNode;
  className?: string;
  showIcon?: boolean;
};

export function ExternalLink({ href, children, className, showIcon = true }: ExternalLinkProps) {
  const safe = safeHref(href);
  const label = children ?? prettyUrl(href);
  if (!safe) return <span className={cn("break-all", className)}>{label}</span>;
  return (
    <a
      href={safe}
      target="_blank"
      rel="noopener noreferrer nofollow"
      className={cn("inline-flex min-w-0 items-center gap-1 underline-offset-4 hover:underline", className)}
    >
      <span className="min-w-0 truncate">{label}</span>
      {showIcon ? <ExternalLinkIcon className="size-3 shrink-0 opacity-60" aria-hidden="true" /> : null}
      <span className="sr-only"> (opens in a new tab)</span>
    </a>
  );
}

type EntityLinkProps = {
  wid: string;
  entity: EntityRef | null | undefined;
  className?: string;
};

export function EntityLink({ wid, entity, className }: EntityLinkProps) {
  if (!entity) return null;
  return (
    <Link
      href={routes.entity(wid, entity.id)}
      className={cn("font-medium underline-offset-4 hover:text-brand hover:underline", className)}
    >
      {entity.name}
    </Link>
  );
}
