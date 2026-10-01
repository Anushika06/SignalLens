import type { Metadata } from "next";

import { WorldScreen } from "@/components/world/world-screen";

export const metadata: Metadata = { title: "World state" };

export default async function Page({ params }: PageProps<"/w/[wid]/world">) {
  const { wid } = await params;
  return <WorldScreen wid={wid} />;
}
