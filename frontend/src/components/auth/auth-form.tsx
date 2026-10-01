"use client";

import { useState } from "react";
import { AlertTriangle, FlaskConical } from "lucide-react";
import { mutate } from "swr";

import { errorMessage } from "@/components/common/states";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Field, FieldDescription, FieldError, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Spinner } from "@/components/ui/spinner";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { api, isApiError, paths } from "@/lib/api";
import { useSystemConfig } from "@/lib/hooks";
import type { Me } from "@/lib/types";

import { SsoSignIn } from "./sso-sign-in";

type Mode = "signin" | "signup";
type Values = { name: string; org_name: string; email: string; password: string };
type Errors = Partial<Record<keyof Values, string>>;

/** Seeded by `signallens seed-demo` (contract §2). */
const DEMO_ACCOUNT = { email: "demo@signallens.app", password: "signallens-demo" };
const MIN_PASSWORD = 8;

const FIELD_ORDER: (keyof Values)[] = ["name", "org_name", "email", "password"];
const fieldId = (mode: Mode, key: keyof Values) => `${mode}-${key}`;

function validate(mode: Mode, values: Values): Errors {
  const errors: Errors = {};
  if (mode === "signup") {
    if (!values.name.trim()) errors.name = "Enter your name.";
    if (!values.org_name.trim()) errors.org_name = "Enter your organisation's name.";
  }
  if (!/^\S+@\S+\.\S+$/.test(values.email.trim())) errors.email = "Enter a valid email address.";
  if (mode === "signin" && !values.password) errors.password = "Enter your password.";
  if (mode === "signup" && values.password.length < MIN_PASSWORD) {
    errors.password = `Use at least ${MIN_PASSWORD} characters.`;
  }
  return errors;
}

type TextFieldProps = React.ComponentProps<typeof Input> & {
  id: string;
  label: string;
  error?: string;
  hint?: string;
};

function TextField({ id, label, error, hint, ...inputProps }: TextFieldProps) {
  const describedBy = [error ? `${id}-error` : null, hint ? `${id}-hint` : null].filter(Boolean).join(" ");
  return (
    <Field data-invalid={error ? true : undefined}>
      <FieldLabel htmlFor={id}>{label}</FieldLabel>
      <Input id={id} aria-invalid={error ? true : undefined} aria-describedby={describedBy || undefined} {...inputProps} />
      {hint && !error ? <FieldDescription id={`${id}-hint`}>{hint}</FieldDescription> : null}
      {error ? <FieldError id={`${id}-error`}>{error}</FieldError> : null}
    </Field>
  );
}

/**
 * Sign in / create account. Auth calls never trigger the global 401 redirect, so a wrong
 * password shows up here as an inline message.
 */
export function AuthForm({
  onSuccess,
  next = "/",
  ssoError = null,
}: {
  onSuccess: (me: Me) => void;
  /** Where single sign-on returns to (already validated by safeNextPath). */
  next?: string;
  /** `?sso_error=` from a failed single sign-on attempt. */
  ssoError?: string | null;
}) {
  const [mode, setMode] = useState<Mode>("signin");
  const [values, setValues] = useState<Values>({ name: "", org_name: "", email: "", password: "" });
  const [errors, setErrors] = useState<Errors>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  // The shortcut is shown only where the backend says a demo account is meant to be used.
  const { data: config } = useSystemConfig();
  const showDemo = config?.demo_login === true;

  const set = (key: keyof Values) => (event: React.ChangeEvent<HTMLInputElement>) => {
    setValues((current) => ({ ...current, [key]: event.target.value }));
    if (errors[key]) setErrors((current) => ({ ...current, [key]: undefined }));
  };

  function switchMode(next: string) {
    setMode(next as Mode);
    setErrors({});
    setFormError(null);
  }

  function fillDemoAccount() {
    setMode("signin");
    setErrors({});
    setFormError(null);
    setValues((current) => ({ ...current, ...DEMO_ACCOUNT }));
  }

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const found = validate(mode, values);
    setErrors(found);
    const firstInvalid = FIELD_ORDER.find((key) => found[key]);
    if (firstInvalid) {
      document.getElementById(fieldId(mode, firstInvalid))?.focus();
      return;
    }
    setPending(true);
    setFormError(null);
    try {
      const email = values.email.trim();
      const me =
        mode === "signin"
          ? await api.auth.login({ email, password: values.password })
          : await api.auth.signup({
              email,
              password: values.password,
              name: values.name.trim(),
              org_name: values.org_name.trim(),
            });
      // Prime the session cache so the workspace shell shows the user immediately.
      await mutate(paths.me, me, { revalidate: false });
      onSuccess(me);
    } catch (error) {
      setFormError(
        mode === "signin" && isApiError(error) && error.status === 401
          ? "That email and password don't match. Check them and try again."
          : errorMessage(error),
      );
      setPending(false);
    }
  }

  const form = (current: Mode) => (
    <form onSubmit={submit} noValidate className="space-y-5">
      <FieldGroup className="gap-4">
        {current === "signup" ? (
          <>
            <TextField
              id={fieldId(current, "name")}
              label="Your name"
              autoComplete="name"
              value={values.name}
              onChange={set("name")}
              error={errors.name}
            />
            <TextField
              id={fieldId(current, "org_name")}
              label="Organisation"
              autoComplete="organization"
              value={values.org_name}
              onChange={set("org_name")}
              error={errors.org_name}
            />
          </>
        ) : null}
        <TextField
          id={fieldId(current, "email")}
          label="Work email"
          type="email"
          inputMode="email"
          autoComplete="email"
          value={values.email}
          onChange={set("email")}
          error={errors.email}
        />
        <TextField
          id={fieldId(current, "password")}
          label="Password"
          type="password"
          autoComplete={current === "signin" ? "current-password" : "new-password"}
          value={values.password}
          onChange={set("password")}
          error={errors.password}
          hint={current === "signup" ? `At least ${MIN_PASSWORD} characters.` : undefined}
        />
      </FieldGroup>
      {formError ? (
        <Alert variant="destructive">
          <AlertTriangle aria-hidden="true" />
          <AlertDescription>{formError}</AlertDescription>
        </Alert>
      ) : null}
      <Button type="submit" size="lg" className="w-full" disabled={pending}>
        {pending ? <Spinner /> : null}
        {current === "signin" ? "Sign in" : "Create account"}
      </Button>
    </form>
  );

  return (
    <div className="space-y-4">
      <Card>
        <CardContent className="space-y-5">
          <SsoSignIn next={next} error={ssoError} />
          <Tabs value={mode} onValueChange={switchMode} className="gap-5">
            <TabsList className="w-full">
              <TabsTrigger value="signin">Sign in</TabsTrigger>
              <TabsTrigger value="signup">Create account</TabsTrigger>
            </TabsList>
            <TabsContent value="signin">{form("signin")}</TabsContent>
            <TabsContent value="signup">{form("signup")}</TabsContent>
          </Tabs>
        </CardContent>
      </Card>
      {showDemo ? (
        <p className="flex flex-wrap items-center justify-center gap-x-1 text-center text-xs text-muted-foreground">
          <span>Exploring SignalLens?</span>
          <Button type="button" variant="link" size="xs" className="h-auto px-0 text-xs" onClick={fillDemoAccount}>
            <FlaskConical aria-hidden="true" />
            Use the demo account
          </Button>
        </p>
      ) : null}
    </div>
  );
}
