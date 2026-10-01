"use client";

import { useState } from "react";
import { AlertTriangle, KeyRound } from "lucide-react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { ssoStartUrl } from "@/lib/api";
import { useSsoConfig } from "@/lib/hooks";

/** The `sso_error` codes the backend's SSO callback can send back to /login. */
export function ssoErrorMessage(code: string, provider: string): string {
  switch (code) {
    case "not_configured":
      return "Single sign-on isn't set up on this SignalLens server. Sign in with your email and password.";
    case "access_denied":
      return `Sign-in was cancelled at ${provider}.`;
    case "provider_error":
      return `${provider} reported a problem with the sign-in. Try again.`;
    case "provider_unavailable":
      return `Couldn't reach ${provider}. Try again in a moment.`;
    case "invalid_state":
      return "Your sign-in attempt expired or was started in another tab or browser. Try again.";
    case "token_exchange_failed":
      return `${provider} didn't confirm the sign-in. Try again.`;
    case "invalid_token":
      return `The sign-in response from ${provider} couldn't be verified. Try again.`;
    case "email_missing":
      return `${provider} didn't share your email address, so SignalLens can't identify your account.`;
    case "email_unverified":
      return `Your email address isn't verified with ${provider}. Verify it there, then try again.`;
    case "domain_not_allowed":
      return "Your email domain isn't allowed to sign in here. Use your work account.";
    case "account_conflict":
      return `This email is already linked to a different ${provider} account. Ask your administrator for help.`;
    default:
      return "Single sign-on didn't work. Try again, or sign in with your email and password.";
  }
}

/**
 * "Continue with Google" (or the configured provider). Shown only when the backend reports SSO
 * as enabled; the click is a full navigation because the backend redirects to the provider.
 */
export function SsoSignIn({ next, error }: { next: string; error: string | null }) {
  const { data: sso } = useSsoConfig();
  const [leaving, setLeaving] = useState(false);
  const provider = sso?.provider_name || "your identity provider";
  if (!error && !sso?.enabled) return null;

  return (
    <div className="space-y-4">
      {error ? (
        <Alert variant="destructive">
          <AlertTriangle aria-hidden="true" />
          <AlertDescription>{ssoErrorMessage(error, provider)}</AlertDescription>
        </Alert>
      ) : null}
      {sso?.enabled ? (
        <>
          <Button asChild variant="outline" size="lg" className="w-full">
            <a href={ssoStartUrl(next)} onClick={() => setLeaving(true)} aria-busy={leaving || undefined}>
              {leaving ? <Spinner /> : <KeyRound aria-hidden="true" />}
              Continue with {sso.provider_name}
            </a>
          </Button>
          <div className="flex items-center gap-3 text-xs text-muted-foreground" aria-hidden="true">
            <span className="h-px flex-1 bg-border" />
            or use your email
            <span className="h-px flex-1 bg-border" />
          </div>
        </>
      ) : null}
    </div>
  );
}
