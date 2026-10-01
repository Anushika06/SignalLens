"use client";

import { useState } from "react";
import Link from "next/link";
import { History, ShieldCheck, UserCheck } from "lucide-react";

import { PageHeader } from "@/components/common/page-header";
import { ListSkeleton } from "@/components/common/skeletons";
import { EmptyState, ErrorState } from "@/components/common/states";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useApprovals, useWorkspace } from "@/lib/hooks";
import { routes } from "@/lib/routes";
import type { Approval, WorkspaceRole } from "@/lib/types";

import { ApprovalCard } from "./approval-card";

type Tab = "pending" | "decided";

const ROLE_LABEL: Record<WorkspaceRole, string> = { owner: "Owner", admin: "Admin", member: "Member" };

const newestFirst = (key: (approval: Approval) => string | null) => (a: Approval, b: Approval) =>
  new Date(key(b) ?? b.created_at).getTime() - new Date(key(a) ?? a.created_at).getTime();

function Count({ value }: { value: number | undefined }) {
  if (value === undefined) return null;
  return (
    <span className="metric rounded-md bg-muted px-1.5 text-xs text-muted-foreground group-data-[state=active]:bg-primary/10 group-data-[state=active]:text-brand">
      {value}
    </span>
  );
}

function ApprovalList({ wid, approvals }: { wid: string; approvals: Approval[] }) {
  return (
    <ul className="space-y-4">
      {approvals.map((approval) => (
        <li key={approval.id}>
          <ApprovalCard wid={wid} approval={approval} />
        </li>
      ))}
    </ul>
  );
}

/**
 * The human-in-the-loop queue. Agents research and notify on their own, but any action that
 * leaves the company waits here for a person's decision.
 */
export function ApprovalsScreen({ wid }: { wid: string }) {
  const [tab, setTab] = useState<Tab>("pending");
  const pendingQuery = useApprovals(wid, "pending");
  const allQuery = useApprovals(wid);
  const myRole = useWorkspace(wid).data?.my_role;

  const pending = pendingQuery.data ? [...pendingQuery.data].sort(newestFirst((a) => a.created_at)) : undefined;
  const decided = allQuery.data
    ? allQuery.data.filter((approval) => approval.status !== "pending").sort(newestFirst((a) => a.decided_at))
    : undefined;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Approvals"
        description="Actions an agent (or a teammate) wants to take outside your company. Nothing leaves SignalLens until a person approves it."
      />

      <div className="flex gap-3 rounded-xl border bg-card px-4 py-3.5">
        <ShieldCheck className="mt-0.5 size-5 shrink-0 text-brand" aria-hidden="true" />
        <div className="space-y-1 text-sm">
          <p className="font-medium">SignalLens never acts externally on its own.</p>
          <p className="text-pretty text-muted-foreground">
            Agents research, verify and notify your teams autonomously. Sending an email, sharing a card outside the
            company or posting to a partner&apos;s webhook always waits here for a human decision — agents can only
            propose.
          </p>
          <p className="text-pretty text-muted-foreground" data-testid="approver-rule">
            <span className="font-medium text-foreground">Approvers: owners and admins; you can&apos;t approve your own
            request</span>{" "}
            (unless you&apos;re the only approver — then it&apos;s recorded as self-approved).
            {myRole ? (
              <>
                {" "}
                Your role here: <span className="font-medium text-foreground">{ROLE_LABEL[myRole]}</span>.
              </>
            ) : null}{" "}
            <Link
              href={`${routes.settings(wid)}#members`}
              className="font-medium text-foreground/80 underline-offset-4 hover:text-brand hover:underline"
            >
              Members &amp; roles
            </Link>
          </p>
        </div>
      </div>

      <Tabs value={tab} onValueChange={(value) => setTab(value as Tab)}>
        <TabsList variant="line" className="w-full justify-start border-b pb-0">
          <TabsTrigger value="pending" className="group flex-none">
            Pending <Count value={pending?.length} />
          </TabsTrigger>
          <TabsTrigger value="decided" className="group flex-none">
            Decided <Count value={decided?.length} />
          </TabsTrigger>
        </TabsList>

        <TabsContent value="pending" className="pt-4">
          {pendingQuery.error && !pending ? (
            <ErrorState error={pendingQuery.error} onRetry={() => void pendingQuery.mutate()} />
          ) : !pending ? (
            <ListSkeleton rows={3} />
          ) : pending.length === 0 ? (
            <EmptyState
              icon={UserCheck}
              title="Nothing is waiting for you"
              description="When an agent proposes an action outside your company — emailing an advisor, sharing a card externally, posting to a partner webhook — it appears here. Nothing is sent until someone approves it."
            />
          ) : (
            <ApprovalList wid={wid} approvals={pending} />
          )}
        </TabsContent>

        <TabsContent value="decided" className="pt-4">
          {allQuery.error && !decided ? (
            <ErrorState error={allQuery.error} onRetry={() => void allQuery.mutate()} />
          ) : !decided ? (
            <ListSkeleton rows={3} />
          ) : decided.length === 0 ? (
            <EmptyState
              icon={History}
              title="No decisions yet"
              description="Approved and rejected actions are kept here, with who decided and what happened, as an audit trail."
            />
          ) : (
            <ApprovalList wid={wid} approvals={decided} />
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
}
