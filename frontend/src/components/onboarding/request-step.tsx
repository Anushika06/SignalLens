"use client";

import { Database, Radar, Search, UserCheck } from "lucide-react";

import { Section } from "@/components/common/page-header";
import { Button } from "@/components/ui/button";
import { Field, FieldDescription, FieldError, FieldLabel } from "@/components/ui/field";
import { Textarea } from "@/components/ui/textarea";

const EXAMPLES = [
  "I want to monitor Razorpay",
  "Monitor Stripe's pricing and product launches",
  "Monitor Tata Motors' EV business",
  "Monitor Pfizer's pipeline and regulatory approvals",
];

const NEXT_STEPS = [
  {
    icon: Search,
    title: "Research",
    body: "The planner researches the subject, the companies and regulators around it, and the best sources to watch.",
  },
  {
    icon: UserCheck,
    title: "Your approval",
    body: "You review the proposed entities, areas and sources. Nothing is monitored until you approve.",
  },
  {
    icon: Database,
    title: "Baseline",
    body: "SignalLens records the current state and can replay about a year of web-archive history. The first check never alerts.",
  },
  {
    icon: Radar,
    title: "Monitoring",
    body: "Material changes are verified with quoted evidence, explained for your company and routed to the right teams.",
  },
];

type RequestStepProps = {
  value: string;
  onChange: (value: string) => void;
  error: string | null;
  /** Shown when the workspace name was left blank. */
  derivedName: string | null;
  /** Ctrl/⌘ + Enter submits. */
  onSubmitShortcut: () => void;
};

/** Step 2: the monitoring request in plain language, with examples and what happens next. */
export function RequestStep({ value, onChange, error, derivedName, onSubmitShortcut }: RequestStepProps) {
  return (
    <div className="space-y-10">
      <div className="space-y-4">
        <Field data-invalid={error ? true : undefined}>
          <FieldLabel htmlFor="monitoring-request">Monitoring request</FieldLabel>
          <Textarea
            id="monitoring-request"
            value={value}
            onChange={(event) => onChange(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
                event.preventDefault();
                onSubmitShortcut();
              }
            }}
            rows={5}
            className="min-h-32 text-base md:text-base"
            placeholder="I want to monitor Razorpay — especially pricing, partnerships and RBI regulation."
            aria-invalid={error ? true : undefined}
            aria-describedby={error ? "monitoring-request-error" : "monitoring-request-hint"}
          />
          {error ? (
            <FieldError id="monitoring-request-error">{error}</FieldError>
          ) : (
            <FieldDescription id="monitoring-request-hint">
              Brief it the way you would brief an analyst. A company name is enough; mention what you care about to
              focus the plan.
            </FieldDescription>
          )}
        </Field>

        <div className="space-y-2">
          <p id="request-examples" className="text-xs font-medium text-muted-foreground">
            Try an example
          </p>
          <div role="group" aria-labelledby="request-examples" className="flex flex-wrap gap-2">
            {EXAMPLES.map((example) => (
              <Button
                key={example}
                type="button"
                variant="outline"
                size="sm"
                aria-pressed={value === example}
                onClick={() => onChange(example)}
                className="h-auto py-1.5 text-left whitespace-normal aria-pressed:border-brand/40 aria-pressed:bg-brand/5"
              >
                {example}
              </Button>
            ))}
          </div>
        </div>

        {derivedName ? (
          <p className="text-sm text-muted-foreground">
            We&apos;ll call this workspace <span className="font-medium text-foreground">“{derivedName}”</span>. You can
            rename it later in Settings.
          </p>
        ) : null}
      </div>

      <Section title="What happens next">
        <ol className="grid gap-3 sm:grid-cols-2">
          {NEXT_STEPS.map((step, index) => (
            <li key={step.title} className="flex gap-3 rounded-xl border bg-card p-4">
              <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-muted text-muted-foreground">
                <step.icon className="size-4" aria-hidden="true" />
              </span>
              <div className="min-w-0 space-y-1">
                <p className="text-sm font-medium">
                  <span className="metric mr-1 text-muted-foreground">{index + 1}.</span>
                  {step.title}
                </p>
                <p className="text-sm text-pretty text-muted-foreground">{step.body}</p>
              </div>
            </li>
          ))}
        </ol>
      </Section>
    </div>
  );
}
