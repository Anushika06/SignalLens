"use client";

import { ThemeProvider } from "next-themes";
import { SWRConfig } from "swr";

import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { ApiError, fetcher } from "@/lib/api";

/** App-wide providers: theme (class strategy, follows the system by default), SWR, tooltips, toasts. */
export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <ThemeProvider attribute="class" defaultTheme="system" enableSystem disableTransitionOnChange>
      <SWRConfig
        value={{
          fetcher,
          // Client errors (bad id, no access, not signed in) won't fix themselves — don't retry them.
          onErrorRetry: (error, _key, _config, revalidate, { retryCount }) => {
            if (error instanceof ApiError && error.status >= 400 && error.status < 500) return;
            if (retryCount >= 3) return;
            setTimeout(() => revalidate({ retryCount }), 1500 * 2 ** retryCount);
          },
        }}
      >
        <TooltipProvider delayDuration={250}>
          {children}
          <Toaster position="bottom-right" closeButton />
        </TooltipProvider>
      </SWRConfig>
    </ThemeProvider>
  );
}
