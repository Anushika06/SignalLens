import Link from "next/link";
import { Eye, Lightbulb, type LucideIcon, Scale, Sparkles, Users } from "lucide-react";

import { Chip } from "@/components/common/badges";
import { TextBlock } from "@/components/common/page-header";
import { routes } from "@/lib/routes";
import type { ReportDetail } from "@/lib/types";

function AssessmentList({ title, icon: Icon, items }: { title: string; icon: LucideIcon; items: string[] }) {
  if (items.length === 0) return null;
  return (
    <div className="space-y-2">
      <h3 className="flex items-center gap-1.5 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
        <Icon className="size-3.5" aria-hidden="true" />
        {title}
      </h3>
      <ul className="space-y-1.5 text-sm leading-relaxed">
        {items.map((item, index) => (
          <li key={index} className="flex gap-2 text-pretty">
            <span aria-hidden="true" className="mt-2 size-1 shrink-0 rounded-full bg-muted-foreground/60" />
            <span>{item}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/**
 * The impact analyst's reading of the change for *this* company. Visually and verbally set
 * apart from "What changed" so nobody mistakes interpretation for fact.
 */
export function WhyItMatters({ wid, report }: { wid: string; report: ReportDetail }) {
  return (
    <section
      id="why-it-matters"
      aria-labelledby="why-it-matters-title"
      className="scroll-mt-20 rounded-xl border border-brand/20 bg-brand/5 p-4 sm:p-5"
    >
      <header className="flex items-start gap-3">
        <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-brand/10 text-brand">
          <Sparkles className="size-4" aria-hidden="true" />
        </span>
        <div className="min-w-0">
          <h2 id="why-it-matters-title" className="text-sm font-semibold tracking-tight">
            Why it matters to you
          </h2>
          <p className="text-xs text-muted-foreground">
            <span className="font-medium text-brand">Agent assessment</span> — interpretation, not fact
          </p>
        </div>
      </header>

      <TextBlock text={report.why_it_matters} className="mt-4" />

      <div className="mt-5 space-y-5">
        <AssessmentList title="Assumptions" icon={Scale} items={report.assumptions} />
        <AssessmentList title="Considerations" icon={Lightbulb} items={report.considerations} />
        <AssessmentList title="Watch next" icon={Eye} items={report.watch_next} />
      </div>

      {report.affected_teams.length > 0 ? (
        <div className="mt-5 space-y-2 border-t border-brand/15 pt-4">
          <h3 className="flex items-center gap-1.5 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
            <Users className="size-3.5" aria-hidden="true" />
            Who needs to know
          </h3>
          <ul className="flex flex-wrap gap-1.5" aria-label="Affected teams">
            {report.affected_teams.map((team) => (
              <li key={team.id}>
                <Chip className="h-6 px-2 text-foreground/80">{team.name}</Chip>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      <p className="mt-4 text-xs text-pretty text-muted-foreground">
        Grounded in your{" "}
        <Link href={routes.settings(wid)} className="underline underline-offset-2 hover:text-foreground">
          company profile
        </Link>
        . Keeping it current makes these assessments sharper.
      </p>
    </section>
  );
}
