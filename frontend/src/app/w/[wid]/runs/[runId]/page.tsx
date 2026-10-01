import type { Metadata } from "next";

import { RunScreen } from "@/components/runs/run-screen";

export const metadata: Metadata = { title: "Run trace" };

export default async function Page({ params }: PageProps<"/w/[wid]/runs/[runId]">) {
  const { wid, runId } = await params;
  return <RunScreen wid={wid} runId={runId} />;
}
