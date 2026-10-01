import type { Metadata } from "next";

import { PlanScreen } from "@/components/plan/plan-screen";

export const metadata: Metadata = { title: "Monitoring plan" };

export default async function Page({ params }: PageProps<"/w/[wid]/plan/[pid]">) {
  const { wid, pid } = await params;
  return <PlanScreen wid={wid} pid={pid} />;
}
