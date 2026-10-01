import type { Metadata } from "next";

import { ApprovalsScreen } from "@/components/approvals/approvals-screen";

export const metadata: Metadata = { title: "Approvals" };

export default async function Page({ params }: PageProps<"/w/[wid]/approvals">) {
  const { wid } = await params;
  return <ApprovalsScreen wid={wid} />;
}
