import { Suspense } from "react";
import type { Metadata } from "next";

import { ReportFeedScreen } from "@/components/intel/report-feed-screen";

export const metadata: Metadata = { title: "Intelligence" };

export default async function Page({ params }: PageProps<"/w/[wid]/intel">) {
  const { wid } = await params;
  return (
    <Suspense>
      <ReportFeedScreen wid={wid} />
    </Suspense>
  );
}
