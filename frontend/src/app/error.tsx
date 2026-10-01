"use client";

import { useEffect } from "react";

import { ErrorState } from "@/components/common/states";

/** Last-resort boundary for unexpected rendering errors. */
export default function Error({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <main className="mx-auto flex min-h-[60svh] max-w-lg items-center px-4">
      <ErrorState
        className="w-full"
        title="Something went wrong on this page"
        error={new globalThis.Error("An unexpected error occurred. Try again, or reload the page.")}
        onRetry={reset}
      />
    </main>
  );
}
