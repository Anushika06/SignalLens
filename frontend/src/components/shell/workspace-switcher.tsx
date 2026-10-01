"use client";

import Link from "next/link";
import { Check, ChevronsUpDown, LayoutGrid, Plus } from "lucide-react";

import { LogoMark } from "@/components/common/logo";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { SidebarMenu, SidebarMenuButton, SidebarMenuItem, useSidebar } from "@/components/ui/sidebar";
import { Skeleton } from "@/components/ui/skeleton";
import { useWorkspace, useWorkspaces } from "@/lib/hooks";
import { WORKSPACE_STATUS } from "@/lib/labels";
import { routes } from "@/lib/routes";

export function WorkspaceSwitcher({ wid }: { wid: string }) {
  const { data: workspace, isLoading } = useWorkspace(wid);
  const { data: workspaces } = useWorkspaces();
  const { isMobile } = useSidebar();

  return (
    <SidebarMenu>
      <SidebarMenuItem>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <SidebarMenuButton size="lg" className="data-open:bg-sidebar-accent" aria-label="Switch workspace">
              <LogoMark className="size-8" />
              <span className="grid min-w-0 flex-1 text-left leading-tight">
                {isLoading ? (
                  <Skeleton className="h-3.5 w-28" />
                ) : (
                  <>
                    <span className="truncate text-sm font-semibold">{workspace?.name ?? "Workspace"}</span>
                    <span className="truncate text-xs text-muted-foreground">
                      {workspace ? WORKSPACE_STATUS[workspace.status].label : "SignalLens"}
                    </span>
                  </>
                )}
              </span>
              <ChevronsUpDown className="ml-auto" aria-hidden="true" />
            </SidebarMenuButton>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start" side={isMobile ? "bottom" : "right"} className="w-64">
            <DropdownMenuLabel className="text-xs text-muted-foreground">Workspaces</DropdownMenuLabel>
            {(workspaces ?? []).map((item) => (
              <DropdownMenuItem key={item.id} asChild>
                <Link href={routes.dashboard(item.id)} aria-current={item.id === wid ? "page" : undefined}>
                  <span className="min-w-0 flex-1 truncate">{item.name}</span>
                  {item.unread_reports > 0 ? (
                    <span className="metric text-xs text-muted-foreground">{item.unread_reports} new</span>
                  ) : null}
                  {item.id === wid ? <Check aria-hidden="true" /> : null}
                </Link>
              </DropdownMenuItem>
            ))}
            <DropdownMenuSeparator />
            <DropdownMenuItem asChild>
              <Link href={routes.newWorkspace}>
                <Plus aria-hidden="true" />
                New workspace
              </Link>
            </DropdownMenuItem>
            <DropdownMenuItem asChild>
              <Link href={routes.home}>
                <LayoutGrid aria-hidden="true" />
                All workspaces
              </Link>
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </SidebarMenuItem>
    </SidebarMenu>
  );
}
