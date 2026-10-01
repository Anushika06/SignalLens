import { routes } from "@/lib/routes";
import type { RunSubjectType, RunSummary } from "@/lib/types";

/** What a run was about, in words. */
export const RUN_SUBJECT_LABEL: Record<RunSubjectType, string> = {
  event: "Detected change",
  policy: "Monitoring plan",
  source: "Source",
  report: "Intelligence card",
};

/** Where to go to see a run's subject. A plan id is a policy id, so policies open the plan page. */
export function runSubjectHref(wid: string, subject: RunSummary["subject"]): string | null {
  if (!subject) return null;
  switch (subject.type) {
    case "report":
      return routes.report(wid, subject.id);
    case "policy":
      return routes.plan(wid, subject.id);
    case "source":
      return routes.source(wid, subject.id);
    case "event":
      return routes.filteredEvent(wid, subject.id);
  }
}
