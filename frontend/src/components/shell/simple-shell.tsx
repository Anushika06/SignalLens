"use client";

import Link from "next/link";

import { cn } from "@/lib/utils";
import { Logo } from "@/components/common/logo";
import { ThemeToggle } from "@/components/common/theme-toggle";

import { ConfigBanner } from "./config-banner";
import { CompactUserMenu } from "./user-menu";

type SimpleShellProps = {
  children: React.ReactNode;
  /** Extra header content next to the logo (e.g. a back link). */
  headerStart?: React.ReactNode;
  /** "narrow" suits forms and wizards; "wide" suits lists and editors. */
  width?: "narrow" | "default" | "wide";
  /** Hide the account menu (e.g. on the login page). */
  signedOut?: boolean;
};

const WIDTH = { narrow: "max-w-3xl", default: "max-w-5xl", wide: "max-w-7xl" } as const;

/** Frame for pages outside a workspace: the workspace list, onboarding and the demo lab. */
export function SimpleShell({ children, headerStart, width = "default", signedOut = false }: SimpleShellProps) {
  return (
    <div className="flex min-h-svh flex-col">
      <a
        href="#content"
        className="sr-only z-50 rounded-md bg-background px-3 py-2 text-sm font-medium shadow focus:not-sr-only focus:fixed focus:top-2 focus:left-2"
      >
        Skip to content
      </a>
      <header className="sticky top-0 z-20 border-b bg-background/85 backdrop-blur supports-backdrop-filter:bg-background/70">
        <div className={cn("mx-auto flex h-14 w-full items-center gap-3 px-4 sm:px-6", WIDTH[width])}>
          <Link href="/" aria-label="SignalLens — all workspaces" className="rounded-md">
            <Logo />
          </Link>
          {headerStart ? <div className="flex min-w-0 items-center gap-2">{headerStart}</div> : null}
          <div className="ml-auto flex items-center gap-1">
            <ThemeToggle />
            {signedOut ? null : <CompactUserMenu />}
          </div>
        </div>
      </header>
      {signedOut ? null : <ConfigBanner />}
      <main id="content" tabIndex={-1} className="flex-1 outline-none">
        <div className={cn("mx-auto w-full px-4 py-8 sm:px-6 sm:py-10", WIDTH[width])}>{children}</div>
      </main>
    </div>
  );
}
