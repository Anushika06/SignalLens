"use client";

import { useDeferredValue, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";

import { ToneBadge } from "@/components/common/badges";
import { RelativeTime } from "@/components/common/relative-time";
import { ErrorState, errorMessage } from "@/components/common/states";
import { Button } from "@/components/ui/button";
import { Field, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Spinner } from "@/components/ui/spinner";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { api, paths } from "@/lib/api";
import { revalidate, useSandboxPage } from "@/lib/hooks";
import { routes } from "@/lib/routes";
import type { SandboxPage } from "@/lib/types";

type EditorFormProps = {
  page: SandboxPage;
  /** Workspace the lab was opened from, for the "Open Monitoring" shortcut. */
  from: string | null;
  onDirtyChange: (dirty: boolean) => void;
  onSaved: (page: SandboxPage) => void;
};

/**
 * Title + HTML editor with a live preview. The preview is an iframe with `sandbox=""`, so the
 * page's scripts never run and it can't touch this app.
 */
function EditorForm({ page, from, onDirtyChange, onSaved }: EditorFormProps) {
  const router = useRouter();
  const [baseline, setBaseline] = useState({ title: page.title, html: page.html, updatedAt: page.updated_at });
  const [title, setTitle] = useState(page.title);
  const [html, setHtml] = useState(page.html);
  const [saving, setSaving] = useState(false);
  const previewHtml = useDeferredValue(html);
  const dirty = title !== baseline.title || html !== baseline.html;

  useEffect(() => {
    onDirtyChange(dirty);
  }, [dirty, onDirtyChange]);

  useEffect(() => {
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent) => event.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  function reset() {
    setTitle(baseline.title);
    setHtml(baseline.html);
  }

  async function save() {
    setSaving(true);
    try {
      const saved = await api.sandbox.save(page.slug, { title: title.trim() || baseline.title, html });
      setBaseline({ title: saved.title, html: saved.html, updatedAt: saved.updated_at });
      setTitle(saved.title);
      setHtml(saved.html);
      onSaved(saved);
      void revalidate((path) => path === paths.sandboxPages);
      toast.success("Page saved", {
        description: `The next check of sandbox://${page.slug} will pick up this change.`,
        action: from
          ? { label: "Open Monitoring", onClick: () => router.push(routes.monitoring(from, "sources")) }
          : undefined,
      });
    } catch (error) {
      toast.error("Couldn't save the page", { description: errorMessage(error) });
    } finally {
      setSaving(false);
    }
  }

  return (
    <section aria-labelledby="sandbox-editor-title" className="min-w-0 space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 space-y-0.5">
          <h2 id="sandbox-editor-title" className="truncate text-base font-semibold">
            {baseline.title}
          </h2>
          <p className="flex flex-wrap items-center gap-x-1.5 text-xs text-muted-foreground">
            <code className="font-mono">sandbox://{page.slug}</code>
            <span aria-hidden="true">·</span>
            <span>
              Saved <RelativeTime value={baseline.updatedAt} />
            </span>
          </p>
        </div>
        <div className="flex items-center gap-2">
          {dirty ? <ToneBadge tone="amber">Unsaved changes</ToneBadge> : null}
          <Button variant="outline" size="sm" onClick={reset} disabled={!dirty || saving}>
            Reset
          </Button>
          <Button size="sm" onClick={() => void save()} disabled={!dirty || saving}>
            {saving ? <Spinner aria-hidden="true" /> : null}
            Save page
          </Button>
        </div>
      </div>

      <Field className="max-w-xl">
        <FieldLabel htmlFor="sandbox-title">Page title</FieldLabel>
        <Input id="sandbox-title" value={title} onChange={(event) => setTitle(event.target.value)} disabled={saving} />
      </Field>

      {/* One editor and one preview: tabs on small screens, side by side from lg up. */}
      <Tabs defaultValue="edit" className="gap-3">
        <TabsList className="lg:hidden">
          <TabsTrigger value="edit">Edit HTML</TabsTrigger>
          <TabsTrigger value="preview">Preview</TabsTrigger>
        </TabsList>
        <div className="grid gap-4 lg:grid-cols-2">
          <TabsContent
            value="edit"
            forceMount
            className="min-w-0 space-y-1.5 data-[state=inactive]:hidden lg:data-[state=inactive]:block"
          >
            <Label htmlFor="sandbox-html" className="text-xs text-muted-foreground">
              HTML
            </Label>
            <Textarea
              id="sandbox-html"
              value={html}
              onChange={(event) => setHtml(event.target.value)}
              spellCheck={false}
              autoCapitalize="off"
              autoCorrect="off"
              disabled={saving}
              className="field-sizing-fixed h-[60svh] min-h-80 resize-y font-mono text-xs leading-relaxed md:text-xs"
            />
          </TabsContent>
          <TabsContent
            value="preview"
            forceMount
            className="min-w-0 space-y-1.5 data-[state=inactive]:hidden lg:data-[state=inactive]:block"
          >
            <p className="text-xs text-muted-foreground">Live preview · scripts are disabled</p>
            <iframe
              title={`Preview of ${title || baseline.title}`}
              sandbox=""
              srcDoc={previewHtml}
              className="h-[60svh] min-h-80 w-full rounded-lg border bg-white"
            />
          </TabsContent>
        </div>
      </Tabs>
    </section>
  );
}

function EditorSkeleton() {
  return (
    <div className="space-y-4" aria-busy="true" aria-label="Loading page">
      <Skeleton className="h-5 w-56" />
      <Skeleton className="h-8 w-full max-w-xl" />
      <div className="grid gap-4 lg:grid-cols-2">
        <Skeleton className="h-80" />
        <Skeleton className="hidden h-80 lg:block" />
      </div>
    </div>
  );
}

type SandboxEditorProps = {
  slug: string;
  from: string | null;
  onDirtyChange: (dirty: boolean) => void;
};

/** Loads one sandbox page and hands it to the editor. */
export function SandboxEditor({ slug, from, onDirtyChange }: SandboxEditorProps) {
  const { data: page, error, mutate } = useSandboxPage(slug);
  if (error && !page) return <ErrorState error={error} onRetry={() => void mutate()} />;
  if (!page) return <EditorSkeleton />;
  return (
    <EditorForm
      key={page.slug}
      page={page}
      from={from}
      onDirtyChange={onDirtyChange}
      onSaved={(saved) => void mutate(saved, { revalidate: false })}
    />
  );
}
