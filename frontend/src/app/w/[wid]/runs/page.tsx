import { Suspense } from "react";
import type { Metadata } from "next";

import { RunsScreen } from "@/components/runs/runs-screen";

export const metadata: Metadata = { title: "Agent runs" };

export default async function Page({ params }: PageProps<"/w/[wid]/runs">) {
  const { wid } = await params;
  return (
    <Suspense>
      <RunsScreen wid={wid} />
    </Suspense>
  );
}
