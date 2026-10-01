import { cn } from "@/lib/utils";

type LineKind = "add" | "remove" | "hunk" | "meta" | "context";

function classify(line: string): LineKind {
  if (line.startsWith("+++") || line.startsWith("---")) return "meta";
  if (line.startsWith("@@")) return "hunk";
  if (line.startsWith("+")) return "add";
  if (line.startsWith("-")) return "remove";
  return "context";
}

const LINE_STYLE: Record<LineKind, string> = {
  add: "bg-emerald-500/10 text-emerald-800 dark:text-emerald-300",
  remove: "bg-red-500/10 text-red-800 dark:text-red-300",
  hunk: "text-sky-700 dark:text-sky-300",
  meta: "text-muted-foreground",
  context: "text-muted-foreground",
};

/**
 * A unified-diff excerpt of the page change: added lines green, removed lines red, context
 * muted. Screen readers hear "Added:" / "Removed:" instead of relying on colour. Long lines
 * scroll inside the block, never the page.
 */
export function DiffView({ diff, label = "Page change excerpt" }: { diff: string; label?: string }) {
  const lines = diff.replace(/\n+$/, "").split("\n");
  const added = lines.filter((line) => classify(line) === "add").length;
  const removed = lines.filter((line) => classify(line) === "remove").length;

  return (
    <figure className="space-y-2">
      <figcaption className="flex items-center justify-between gap-2 text-xs text-muted-foreground">
        <span>Diff excerpt</span>
        <span className="metric">
          <span className="text-emerald-700 dark:text-emerald-400">+{added}</span>{" "}
          <span className="text-red-700 dark:text-red-400">−{removed}</span>
          <span className="sr-only">
            {" "}
            ({added} lines added, {removed} lines removed)
          </span>
        </span>
      </figcaption>
      <div
        role="region"
        aria-label={label}
        tabIndex={0}
        className="overflow-x-auto rounded-lg border bg-muted/30 focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
      >
        <pre className="min-w-max py-2 font-mono text-xs leading-5">
          <code>
            {lines.map((line, index) => {
              const kind = classify(line);
              const changed = kind === "add" || kind === "remove";
              const text = changed || (kind === "context" && line.startsWith(" ")) ? line.slice(1) : line;
              return (
                <span key={index} className={cn("flex px-3", LINE_STYLE[kind])}>
                  <span aria-hidden="true" className="w-4 shrink-0 select-none">
                    {kind === "add" ? "+" : kind === "remove" ? "−" : ""}
                  </span>
                  {kind === "add" ? <span className="sr-only">Added: </span> : null}
                  {kind === "remove" ? <span className="sr-only">Removed: </span> : null}
                  <span className="whitespace-pre">{text || " "}</span>
                </span>
              );
            })}
          </code>
        </pre>
      </div>
    </figure>
  );
}
