import type { Metadata } from "next";

import { DashboardScreen } from "@/components/dashboard/dashboard-screen";

export const metadata: Metadata = { title: "Dashboard" };

export default async function Page({ params }: PageProps<"/w/[wid]">) {
  const { wid } = await params;
  return <DashboardScreen wid={wid} />;
}
