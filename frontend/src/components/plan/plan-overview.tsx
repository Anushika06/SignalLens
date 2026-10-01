import { CircleHelp } from "lucide-react";

import { Chip } from "@/components/common/badges";
import { DefinitionList, Section, TextBlock } from "@/components/common/page-header";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import type { MonitoringPlan } from "@/lib/types";

/** The planner's summary of the plan and how it understood the market. */
export function PlanOverview({ spec }: { spec: MonitoringPlan }) {
  const { domain } = spec;
  return (
    <div className="grid gap-4 lg:grid-cols-5">
      <Card className="lg:col-span-3">
        <CardHeader>
          <CardTitle>What the planner proposes</CardTitle>
        </CardHeader>
        <CardContent>
          <TextBlock text={spec.summary || "The planner did not write a summary."} />
        </CardContent>
      </Card>
      <Card className="lg:col-span-2">
        <CardHeader>
          <CardTitle>Domain</CardTitle>
          <CardDescription>How the planner understood the market</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <DefinitionList
            items={[
              { label: "Industry", value: domain.industry || "—" },
              { label: "Sector", value: domain.sector || "—" },
              {
                label: "Geographies",
                value:
                  domain.geographies.length > 0 ? (
                    <span className="flex flex-wrap gap-1">
                      {domain.geographies.map((geography) => (
                        <Chip key={geography} className="text-foreground">
                          {geography}
                        </Chip>
                      ))}
                    </span>
                  ) : (
                    "—"
                  ),
              },
            ]}
          />
          {domain.rationale ? <p className="text-xs text-pretty text-muted-foreground">{domain.rationale}</p> : null}
        </CardContent>
      </Card>
    </div>
  );
}

/** Things the planner could not decide alone — shown before the detail so they inform the review. */
export function OpenQuestions({ questions }: { questions: string[] }) {
  if (questions.length === 0) return null;
  return (
    <Section
      id="questions"
      title="Questions from the planner"
      description="Things it couldn't settle on its own. If any of them changes your mind, adjust the plan below."
    >
      <ul className="space-y-2">
        {questions.map((question) => (
          <li
            key={question}
            className="flex gap-2.5 rounded-lg border border-brand/20 bg-brand/5 px-3 py-2.5 text-sm text-pretty"
          >
            <CircleHelp className="mt-0.5 size-4 shrink-0 text-brand" aria-hidden="true" />
            {question}
          </li>
        ))}
      </ul>
    </Section>
  );
}
