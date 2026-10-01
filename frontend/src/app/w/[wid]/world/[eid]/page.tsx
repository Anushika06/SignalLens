import type { Metadata } from "next";

import { EntityScreen } from "@/components/world/entity-screen";

export const metadata: Metadata = { title: "Entity" };

export default async function Page({ params }: PageProps<"/w/[wid]/world/[eid]">) {
  const { wid, eid } = await params;
  return <EntityScreen wid={wid} eid={eid} />;
}
