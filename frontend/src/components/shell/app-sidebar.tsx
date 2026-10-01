"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Bot,
  FlaskConical,
  Globe2,
  LayoutDashboard,
  Lightbulb,
  type LucideIcon,
  Radar,
  Settings,
  UserCheck,
} from "lucide-react";

import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuBadge,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarRail,
  useSidebar,
} from "@/components/ui/sidebar";
import { useApprovals, useSystemConfig, useWorkspace } from "@/lib/hooks";
import { routes } from "@/lib/routes";

import { SidebarUserMenu } from "./user-menu";
import { WorkspaceSwitcher } from "./workspace-switcher";

type NavItem = {
  label: string;
  icon: LucideIcon;
  href: string;
  /** Exact match only (the dashboard is the prefix of every other route). */
  exact?: boolean;
  badge?: { count: number; label: string };
};

export function AppSidebar({ wid }: { wid: string }) {
  const pathname = usePathname();
  const { setOpenMobile } = useSidebar();
  const { data: workspace } = useWorkspace(wid);
  const { data: pending } = useApprovals(wid, "pending");
  const { data: config } = useSystemConfig();

  const unread = workspace?.unread_reports ?? 0;
  const pendingCount = pending?.length ?? 0;

  const items: NavItem[] = [
    { label: "Dashboard", icon: LayoutDashboard, href: routes.dashboard(wid), exact: true },
    {
      label: "Intelligence",
      icon: Lightbulb,
      href: routes.intel(wid),
      badge: unread ? { count: unread, label: `${unread} unread` } : undefined,
    },
    { label: "World state", icon: Globe2, href: routes.world(wid) },
    { label: "Monitoring", icon: Radar, href: routes.monitoring(wid) },
    { label: "Agent runs", icon: Bot, href: routes.runs(wid) },
    {
      label: "Approvals",
      icon: UserCheck,
      href: routes.approvals(wid),
      badge: pendingCount ? { count: pendingCount, label: `${pendingCount} awaiting your decision` } : undefined,
    },
    { label: "Settings", icon: Settings, href: routes.settings(wid) },
  ];

  const isActive = (item: NavItem) =>
    item.exact ? pathname === item.href : pathname === item.href || pathname.startsWith(`${item.href}/`);

  return (
    <Sidebar collapsible="icon">
      <SidebarHeader>
        <WorkspaceSwitcher wid={wid} />
      </SidebarHeader>
      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupContent>
            <nav aria-label="Workspace">
              <SidebarMenu>
                {items.map((item) => (
                  <SidebarMenuItem key={item.label}>
                    <SidebarMenuButton asChild isActive={isActive(item)} tooltip={item.label}>
                      <Link
                        href={item.href}
                        aria-current={isActive(item) ? "page" : undefined}
                        onClick={() => setOpenMobile(false)}
                      >
                        <item.icon aria-hidden="true" />
                        <span>{item.label}</span>
                        {item.badge ? <span className="sr-only">, {item.badge.label}</span> : null}
                      </Link>
                    </SidebarMenuButton>
                    {item.badge ? (
                      <SidebarMenuBadge
                        aria-hidden="true"
                        className="metric bg-primary/10 text-brand peer-data-active/menu-button:text-brand"
                      >
                        {item.badge.count > 99 ? "99+" : item.badge.count}
                      </SidebarMenuBadge>
                    ) : null}
                  </SidebarMenuItem>
                ))}
              </SidebarMenu>
            </nav>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>
      <SidebarFooter>
        <SidebarMenu>
          {config?.sandbox_enabled ? (
            <SidebarMenuItem>
              <SidebarMenuButton asChild tooltip="Demo lab">
                <Link href={routes.lab(wid)} onClick={() => setOpenMobile(false)}>
                  <FlaskConical aria-hidden="true" />
                  <span>Demo lab</span>
                </Link>
              </SidebarMenuButton>
            </SidebarMenuItem>
          ) : null}
          <SidebarMenuItem>
            <SidebarUserMenu />
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarFooter>
      <SidebarRail />
    </Sidebar>
  );
}
