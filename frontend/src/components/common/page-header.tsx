import { cn } from "@/lib/utils";

type PageHeaderProps = {
  title: React.ReactNode;
  description?: React.ReactNode;
  /** Buttons on the right (they wrap below the title on small screens). */
  actions?: React.ReactNode;
  /** Small line above the title (badges, context). */
  eyebrow?: React.ReactNode;
  className?: string;
};

export function PageHeader({ title, description, actions, eyebrow, className }: PageHeaderProps) {
  return (
    <header className={cn("flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between", className)}>
      <div className="min-w-0 space-y-1.5">
        {eyebrow ? <div className="flex flex-wrap items-center gap-2">{eyebrow}</div> : null}
        <h1 className="text-xl font-semibold tracking-tight text-balance sm:text-2xl">{title}</h1>
        {description ? <p className="max-w-2xl text-sm text-pretty text-muted-foreground">{description}</p> : null}
      </div>
      {actions ? <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div> : null}
    </header>
  );
}

type SectionProps = {
  /** Used for the anchor and aria-labelledby. */
  id?: string;
  title: React.ReactNode;
  description?: React.ReactNode;
  actions?: React.ReactNode;
  className?: string;
  children: React.ReactNode;
};

export function Section({ id, title, description, actions, className, children }: SectionProps) {
  const titleId = id ? `${id}-title` : undefined;
  return (
    <section id={id} aria-labelledby={titleId} className={cn("scroll-mt-20 space-y-3", className)}>
      <div className="flex flex-wrap items-end justify-between gap-x-4 gap-y-2">
        <div className="min-w-0 space-y-0.5">
          <h2 id={titleId} className="text-sm font-semibold tracking-tight">
            {title}
          </h2>
          {description ? <p className="text-sm text-pretty text-muted-foreground">{description}</p> : null}
        </div>
        {actions ? <div className="flex items-center gap-2">{actions}</div> : null}
      </div>
      {children}
    </section>
  );
}

/** Plain text from the API rendered as paragraphs (blank lines separate paragraphs). */
export function TextBlock({ text, className }: { text: string; className?: string }) {
  const paragraphs = text
    .split(/\n\s*\n/)
    .map((paragraph) => paragraph.trim())
    .filter(Boolean);
  return (
    <div className={cn("space-y-3 text-sm leading-relaxed text-pretty", className)}>
      {paragraphs.map((paragraph, index) => (
        <p key={index} className="whitespace-pre-line">
          {paragraph}
        </p>
      ))}
    </div>
  );
}

/** Label/value pairs, e.g. metadata in a header or a detail panel. */
export function DefinitionList({
  items,
  className,
}: {
  items: { label: React.ReactNode; value: React.ReactNode }[];
  className?: string;
}) {
  return (
    <dl className={cn("grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-sm", className)}>
      {items.map((item, index) => (
        <div key={index} className="contents">
          <dt className="text-muted-foreground">{item.label}</dt>
          <dd className="min-w-0">{item.value}</dd>
        </div>
      ))}
    </dl>
  );
}
