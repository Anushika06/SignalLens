import { Suspense } from "react";
import type { Metadata } from "next";

import { MonitoringScreen } from "@/components/monitoring/monitoring-screen";

export const metadata: Metadata = { title: "Monitoring" };

export default async function Page({ params }: PageProps<"/w/[wid]/monitoring">) {
  const { wid } = await params;
  return (
    <Suspense>
      <MonitoringScreen wid={wid} />
    </Suspense>
  );
}
