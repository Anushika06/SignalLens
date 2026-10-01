"use client";

import { useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import { SimpleShell } from "@/components/shell/simple-shell";
import { Spinner } from "@/components/ui/spinner";
import { useOptionalMe } from "@/lib/hooks";

import { AuthForm } from "./auth-form";
import { safeNextPath } from "./safe-next";

/** /login — sign in or create an account, then continue to `?next=` (or the workspace list). */
export function LoginScreen() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const next = safeNextPath(searchParams.get("next"));
  const ssoError = searchParams.get("sso_error");
  const { data: me } = useOptionalMe();

  // Already signed in (e.g. an old bookmark to /login): skip the form.
  useEffect(() => {
    if (me) router.replace(next);
  }, [me, next, router]);

  return (
    <SimpleShell signedOut width="narrow">
      <div className="mx-auto flex w-full max-w-sm flex-col gap-7 py-4 sm:py-10">
        <div className="space-y-2 text-center">
          <h1 className="text-2xl font-semibold tracking-tight text-balance">Welcome to SignalLens</h1>
          <p className="text-sm text-pretty text-muted-foreground">
            Know what materially changed, whether it&apos;s true, why it matters to you, and who needs to know.
          </p>
        </div>
        {me ? (
          <p className="flex items-center justify-center gap-2 text-sm text-muted-foreground" role="status">
            <Spinner />
            Signed in as {me.user.email}. Taking you there…
          </p>
        ) : (
          <AuthForm onSuccess={() => router.replace(next)} next={next} ssoError={ssoError} />
        )}
      </div>
    </SimpleShell>
  );
}
