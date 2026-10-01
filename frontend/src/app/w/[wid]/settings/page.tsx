import type { Metadata } from "next";

import { SettingsScreen } from "@/components/settings/settings-screen";

export const metadata: Metadata = { title: "Settings" };

export default async function Page({ params }: PageProps<"/w/[wid]/settings">) {
  const { wid } = await params;
  return <SettingsScreen wid={wid} />;
}
