"use client";

import Link from "next/link";
import { ChevronsUpDown, LayoutGrid, LogOut, UserRound } from "lucide-react";
import { mutate } from "swr";

import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { SidebarMenuButton, useSidebar } from "@/components/ui/sidebar";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import { useMe } from "@/lib/hooks";
import { routes } from "@/lib/routes";

/** "Priya Raman" → "PR"; a neutral person icon until the user has loaded. */
function initials(name: string | undefined): React.ReactNode {
  const parts = name?.trim().split(/\s+/).filter(Boolean) ?? [];
  const letters = ((parts[0]?.[0] ?? "") + (parts.length > 1 ? (parts.at(-1)?.[0] ?? "") : "")).toUpperCase();
  return letters || <UserRound className="size-3.5" aria-hidden="true" />;
}

export async function logout() {
  try {
    await api.auth.logout();
  } finally {
    // Drop every cached response so nothing from this session survives the sign-out.
    await mutate(() => true, undefined, { revalidate: false });
    window.location.assign(routes.login());
  }
}

function MenuItems() {
  const { data: me } = useMe();
  return (
    <>
      <DropdownMenuLabel className="font-normal">
        <span className="block truncate text-sm font-medium text-foreground">{me?.user.name}</span>
        <span className="block truncate text-xs text-muted-foreground">{me?.user.email}</span>
        {me?.org.name ? <span className="mt-1 block truncate text-xs text-muted-foreground">{me.org.name}</span> : null}
      </DropdownMenuLabel>
      <DropdownMenuSeparator />
      <DropdownMenuGroup>
        <DropdownMenuItem asChild>
          <Link href={routes.home}>
            <LayoutGrid aria-hidden="true" />
            All workspaces
          </Link>
        </DropdownMenuItem>
      </DropdownMenuGroup>
      <DropdownMenuSeparator />
      <DropdownMenuItem onSelect={() => void logout()}>
        <LogOut aria-hidden="true" />
        Log out
      </DropdownMenuItem>
    </>
  );
}

/** User menu in the sidebar footer (shows name and email; collapses to the avatar). */
export function SidebarUserMenu() {
  const { data: me, isLoading } = useMe();
  const { isMobile } = useSidebar();
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <SidebarMenuButton size="lg" className="data-open:bg-sidebar-accent" aria-label="Account menu">
          <Avatar className="size-8 rounded-lg">
            <AvatarFallback className="rounded-lg text-xs">{initials(me?.user.name)}</AvatarFallback>
          </Avatar>
          <span className="grid min-w-0 flex-1 text-left leading-tight">
            {isLoading ? (
              <Skeleton className="h-3.5 w-24" />
            ) : (
              <>
                <span className="truncate text-sm font-medium">{me?.user.name}</span>
                <span className="truncate text-xs text-muted-foreground">{me?.user.email}</span>
              </>
            )}
          </span>
          <ChevronsUpDown className="ml-auto" aria-hidden="true" />
        </SidebarMenuButton>
      </DropdownMenuTrigger>
      <DropdownMenuContent side={isMobile ? "top" : "right"} align="end" className="w-60">
        <MenuItems />
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

/** Avatar-only user menu for pages without the sidebar. */
export function CompactUserMenu() {
  const { data: me } = useMe();
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon" className="rounded-full" aria-label="Account menu">
          <Avatar className="size-7">
            <AvatarFallback className="text-[11px]">{initials(me?.user.name)}</AvatarFallback>
          </Avatar>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-60">
        <MenuItems />
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
