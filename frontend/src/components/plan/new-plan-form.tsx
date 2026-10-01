"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

import { errorMessage } from "@/components/common/states";
import { Button } from "@/components/ui/button";
import { Field, FieldDescription, FieldError, FieldLabel } from "@/components/ui/field";
import { Spinner } from "@/components/ui/spinner";
import { Textarea } from "@/components/ui/textarea";
import { api, paths } from "@/lib/api";
import { revalidate } from "@/lib/hooks";
import { routes } from "@/lib/routes";

type NewPlanFormProps = {
  wid: string;
  /** Prefilled request (usually the previous plan's), editable before submitting. */
  initialText: string;
  submitLabel: string;
  hint?: string;
};

/** Starts a fresh planner run in this workspace and opens its plan page. */
export function NewPlanForm({ wid, initialText, submitLabel, hint }: NewPlanFormProps) {
  const router = useRouter();
  const [text, setText] = useState(initialText);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const requestText = text.trim();
    if (requestText.length < 3) {
      setError("Tell SignalLens what to monitor. A company name is enough.");
      return;
    }
    setPending(true);
    setError(null);
    try {
      const plan = await api.plans.create(wid, { request_text: requestText });
      void revalidate((path) => path === paths.workspace(wid) || path === paths.workspaces);
      router.push(routes.plan(wid, plan.id));
    } catch (caught) {
      setError(errorMessage(caught));
      setPending(false);
    }
  }

  return (
    <form onSubmit={submit} noValidate className="space-y-4 rounded-xl border bg-card p-4">
      <Field data-invalid={error ? true : undefined}>
        <FieldLabel htmlFor="new-plan-request">Monitoring request</FieldLabel>
        <Textarea
          id="new-plan-request"
          value={text}
          onChange={(event) => setText(event.target.value)}
          rows={3}
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? "new-plan-error" : hint ? "new-plan-hint" : undefined}
        />
        {error ? (
          <FieldError id="new-plan-error">{error}</FieldError>
        ) : hint ? (
          <FieldDescription id="new-plan-hint">{hint}</FieldDescription>
        ) : null}
      </Field>
      <div className="flex justify-end">
        <Button type="submit" disabled={pending}>
          {pending ? <Spinner /> : null}
          {submitLabel}
        </Button>
      </div>
    </form>
  );
}
