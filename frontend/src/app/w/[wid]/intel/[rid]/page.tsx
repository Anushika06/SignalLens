import type { Metadata } from "next";

import { ReportScreen } from "@/components/report/report-screen";

export const metadata: Metadata = { title: "Intelligence card" };

export default async function Page({ params }: PageProps<"/w/[wid]/intel/[rid]">) {
  const { wid, rid } = await params;
  return <ReportScreen wid={wid} rid={rid} />;
}
