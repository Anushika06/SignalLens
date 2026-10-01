import { cn } from "@/lib/utils";

/** The user's own words, quoted back — every plan view starts from what was asked. */
export function RequestQuote({ text, className }: { text: string; className?: string }) {
  return (
    <figure className={cn("rounded-xl border bg-muted/30 px-4 py-3", className)}>
      <figcaption className="text-xs font-medium text-muted-foreground">You asked</figcaption>
      <blockquote className="mt-1 text-sm font-medium text-pretty">“{text}”</blockquote>
    </figure>
  );
}
