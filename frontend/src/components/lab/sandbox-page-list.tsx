"use client";

import { cn } from "@/lib/utils";
import { formatRelative } from "@/lib/format";
import type { SandboxPage } from "@/lib/types";

type SandboxPageListProps = {
  pages: SandboxPage[];
  selected: string | null;
  onSelect: (slug: string) => void;
};

/** The fictional pages available in the lab. */
export function SandboxPageList({ pages, selected, onSelect }: SandboxPageListProps) {
  return (
    <nav aria-label="Sandbox pages" className="min-w-0">
      <p className="mb-2 text-xs font-medium text-muted-foreground">Pages</p>
      <ul className="space-y-1">
        {pages.map((page) => {
          const active = page.slug === selected;
          return (
            <li key={page.slug}>
              <button
                type="button"
                onClick={() => onSelect(page.slug)}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "w-full rounded-lg border px-3 py-2.5 text-left transition-colors outline-none hover:bg-muted/60 focus-visible:ring-3 focus-visible:ring-ring/50",
                  active ? "border-primary/40 bg-primary/5 hover:bg-primary/10" : "border-transparent",
                )}
              >
                <span className="block truncate text-sm font-medium">{page.title}</span>
                <span className="block truncate font-mono text-xs text-muted-foreground">sandbox://{page.slug}</span>
                <span className="mt-0.5 block text-xs text-muted-foreground">
                  Updated {formatRelative(page.updated_at)}
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
