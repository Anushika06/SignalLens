"use client";

import { Fragment } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { ThemeToggle } from "@/components/common/theme-toggle";
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "@/components/ui/breadcrumb";
import { Separator } from "@/components/ui/separator";
import { SidebarTrigger } from "@/components/ui/sidebar";
import { routes } from "@/lib/routes";

import { NotificationsBell } from "./notifications-bell";

/** Section titles by first path segment under /w/[wid]. */
const SECTION: Record<string, { title: string; href?: (wid: string) => string }> = {
  "": { title: "Dashboard", href: routes.dashboard },
  intel: { title: "Intelligence", href: (wid) => routes.intel(wid) },
  world: { title: "World state", href: routes.world },
  monitoring: { title: "Monitoring", href: (wid) => routes.monitoring(wid) },
  runs: { title: "Agent runs", href: routes.runs },
  approvals: { title: "Approvals", href: routes.approvals },
  settings: { title: "Settings", href: routes.settings },
  plan: { title: "Monitoring plan" },
};

/** Title for a detail page within a section (sections without an index page have none). */
const DETAIL: Record<string, string> = {
  intel: "Intelligence card",
  world: "Entity",
  runs: "Run trace",
};

function useCrumbs(wid: string) {
  const pathname = usePathname();
  const base = routes.dashboard(wid);
  const rest = pathname.startsWith(base) ? pathname.slice(base.length).split("/").filter(Boolean) : [];
  const sectionKey = rest[0] ?? "";
  const section = SECTION[sectionKey] ?? { title: "SignalLens" };
  const crumbs: { title: string; href?: string }[] = [];
  if (rest.length > 1 && DETAIL[sectionKey]) {
    crumbs.push({ title: section.title, href: section.href?.(wid) });
    crumbs.push({ title: DETAIL[sectionKey] });
  } else {
    crumbs.push({ title: section.title });
  }
  return crumbs;
}

export function TopBar({ wid }: { wid: string }) {
  const crumbs = useCrumbs(wid);
  return (
    <header className="sticky top-0 z-20 flex h-14 shrink-0 items-center gap-2 border-b bg-background/85 px-3 backdrop-blur supports-backdrop-filter:bg-background/70 sm:px-5">
      <SidebarTrigger className="-ml-0.5" aria-label="Toggle navigation" />
      <Separator orientation="vertical" className="mr-1 data-[orientation=vertical]:h-4" />
      <Breadcrumb className="min-w-0 flex-1">
        <BreadcrumbList className="flex-nowrap">
          {crumbs.map((crumb, index) => {
            const last = index === crumbs.length - 1;
            return (
              <Fragment key={crumb.title}>
                <BreadcrumbItem className={last ? "min-w-0" : "hidden sm:inline-flex"}>
                  {last || !crumb.href ? (
                    <BreadcrumbPage className="truncate font-medium">{crumb.title}</BreadcrumbPage>
                  ) : (
                    <BreadcrumbLink asChild>
                      <Link href={crumb.href}>{crumb.title}</Link>
                    </BreadcrumbLink>
                  )}
                </BreadcrumbItem>
                {!last ? <BreadcrumbSeparator className="hidden sm:inline-flex" /> : null}
              </Fragment>
            );
          })}
        </BreadcrumbList>
      </Breadcrumb>
      <div className="flex items-center gap-0.5">
        <NotificationsBell wid={wid} />
        <ThemeToggle />
      </div>
    </header>
  );
}
