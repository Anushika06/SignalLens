"use client";

import { useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { ArrowLeft, FileCode2, FlaskConical } from "lucide-react";

import { PageHeader } from "@/components/common/page-header";
import { EmptyState, ErrorState } from "@/components/common/states";
import { SimpleShell } from "@/components/shell/simple-shell";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useSandboxPages, useSystemConfig } from "@/lib/hooks";
import { routes } from "@/lib/routes";

import { SandboxEditor } from "./sandbox-editor";
import { SandboxPageList } from "./sandbox-page-list";

/** The three steps of a live demo, shown above the editor. */
function HowItWorks({ from }: { from: string | null }) {
  const steps = [
    <>Pick a page and edit its HTML — change a price, add a product, publish a press release.</>,
    <>
      Save. The page is monitored at <code className="font-mono text-xs">sandbox://&lt;slug&gt;</code>, exactly like a
      real website.
    </>,
    <>
      In{" "}
      {from ? (
        <Link href={routes.monitoring(from, "sources")} className="font-medium text-brand underline-offset-4 hover:underline">
          Monitoring
        </Link>
      ) : (
        "Monitoring"
      )}
      , press <span className="font-medium text-foreground">Check now</span> on that source (or wait for its next check)
      and follow the change through detection, materiality and investigation to your dashboard.
    </>,
  ];
  return (
    <ol className="grid gap-3 sm:grid-cols-3">
      {steps.map((step, index) => (
        <li key={index} className="flex gap-3 rounded-xl border bg-card p-4 text-sm text-pretty text-muted-foreground">
          <span
            aria-hidden="true"
            className="metric flex size-6 shrink-0 items-center justify-center rounded-full bg-primary/10 text-xs font-semibold text-brand"
          >
            {index + 1}
          </span>
          <span>{step}</span>
        </li>
      ))}
    </ol>
  );
}

function LabSkeleton() {
  return (
    <div className="grid gap-6 lg:grid-cols-[16rem_1fr]" aria-busy="true" aria-label="Loading">
      <div className="space-y-2">
        <Skeleton className="h-16" />
        <Skeleton className="h-16" />
      </div>
      <Skeleton className="h-96" />
    </div>
  );
}

/** Page picker + editor. Switching pages with unsaved edits asks first. */
function LabWorkbench({ from }: { from: string | null }) {
  const { data: pages, error, isLoading, mutate } = useSandboxPages();
  const [selected, setSelected] = useState<string | null>(null);
  const [dirty, setDirty] = useState(false);
  const [pendingSlug, setPendingSlug] = useState<string | null>(null);

  if (error && !pages) return <ErrorState error={error} onRetry={() => void mutate()} />;
  if (isLoading || !pages) return <LabSkeleton />;
  if (pages.length === 0) {
    return (
      <EmptyState
        icon={FileCode2}
        title="No sandbox pages yet"
        description="The backend serves demo pages here when the lab is enabled. None are defined at the moment."
      />
    );
  }

  const slug = selected && pages.some((page) => page.slug === selected) ? selected : pages[0].slug;

  function select(next: string) {
    if (next === slug) return;
    if (dirty) setPendingSlug(next);
    else setSelected(next);
  }

  return (
    <>
      <div className="grid gap-6 lg:grid-cols-[16rem_1fr]">
        <SandboxPageList pages={pages} selected={slug} onSelect={select} />
        <SandboxEditor key={slug} slug={slug} from={from} onDirtyChange={setDirty} />
      </div>
      <AlertDialog open={pendingSlug !== null} onOpenChange={(open) => (open ? undefined : setPendingSlug(null))}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Discard unsaved changes?</AlertDialogTitle>
            <AlertDialogDescription>
              Your edits to this page haven&apos;t been saved. Switching pages will throw them away.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Keep editing</AlertDialogCancel>
            <AlertDialogAction
              variant="destructive"
              onClick={() => {
                setDirty(false);
                setSelected(pendingSlug);
                setPendingSlug(null);
              }}
            >
              Discard changes
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}

/**
 * Demo lab: fictional pages served by the backend so change detection can be shown on
 * demand. Only available when the backend reports `sandbox_enabled`.
 */
export function DemoLabScreen() {
  const searchParams = useSearchParams();
  const from = searchParams.get("from");
  const { data: config, error: configError, mutate: retryConfig } = useSystemConfig();
  const back = from
    ? { href: routes.dashboard(from), label: "Back to workspace" }
    : { href: routes.home, label: "All workspaces" };

  return (
    <SimpleShell
      width="wide"
      headerStart={
        <Button asChild variant="ghost" size="sm" className="text-muted-foreground">
          <Link href={back.href} aria-label={back.label}>
            <ArrowLeft aria-hidden="true" />
            <span className="hidden sm:inline">{back.label}</span>
          </Link>
        </Button>
      }
    >
      <div className="space-y-6">
        <PageHeader
          eyebrow={
            <span className="inline-flex items-center gap-1.5 text-xs font-medium text-brand">
              <FlaskConical className="size-3.5" aria-hidden="true" />
              For demos
            </span>
          }
          title="Demo lab"
          description="Fictional pages that SignalLens monitors like any other website, so you can demonstrate change detection on demand instead of waiting for a real company to change something."
        />

        {configError && !config ? (
          <ErrorState error={configError} onRetry={() => void retryConfig()} />
        ) : !config ? (
          <LabSkeleton />
        ) : !config.sandbox_enabled ? (
          <EmptyState
            icon={FlaskConical}
            title="The demo lab is turned off"
            description="Sandbox pages are only served when the demo lab is enabled in the backend configuration. Real monitoring is unaffected."
            action={
              <Button asChild variant="outline" size="sm">
                <Link href={back.href}>{back.label}</Link>
              </Button>
            }
          />
        ) : (
          <>
            <HowItWorks from={from} />
            <LabWorkbench from={from} />
          </>
        )}
      </div>
    </SimpleShell>
  );
}
