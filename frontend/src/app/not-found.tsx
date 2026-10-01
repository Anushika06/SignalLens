import Link from "next/link";

import { Logo } from "@/components/common/logo";
import { Button } from "@/components/ui/button";

export default function NotFound() {
  return (
    <main className="flex min-h-svh flex-col items-center justify-center gap-6 px-4 text-center">
      <Logo />
      <div className="space-y-2">
        <h1 className="text-xl font-semibold tracking-tight">This page doesn&apos;t exist</h1>
        <p className="max-w-sm text-sm text-muted-foreground">
          The link may be out of date, or the item may have been removed from this workspace.
        </p>
      </div>
      <Button asChild variant="outline">
        <Link href="/">Back to your workspaces</Link>
      </Button>
    </main>
  );
}
