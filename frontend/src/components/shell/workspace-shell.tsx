"use client";

import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar";

import { AppSidebar } from "./app-sidebar";
import { ConfigBanner } from "./config-banner";
import { TopBar } from "./top-bar";

/**
 * Layout for everything under /w/[wid]: sidebar (a sheet below 768 px), sticky top bar with
 * the page title and notifications, and the API-keys banner when the backend needs keys.
 */
export function WorkspaceShell({
  wid,
  sidebarOpen = true,
  children,
}: {
  wid: string;
  sidebarOpen?: boolean;
  children: React.ReactNode;
}) {
  return (
    <SidebarProvider defaultOpen={sidebarOpen}>
      <a
        href="#content"
        className="sr-only z-50 rounded-md bg-background px-3 py-2 text-sm font-medium shadow focus:not-sr-only focus:fixed focus:top-2 focus:left-2"
      >
        Skip to content
      </a>
      <AppSidebar wid={wid} />
      <SidebarInset className="min-w-0">
        <TopBar wid={wid} />
        <ConfigBanner />
        <div id="content" tabIndex={-1} className="flex-1 px-4 py-6 outline-none sm:px-6 lg:px-8 lg:py-8">
          <div className="mx-auto w-full max-w-7xl">{children}</div>
        </div>
      </SidebarInset>
    </SidebarProvider>
  );
}
