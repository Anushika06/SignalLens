import { Suspense } from "react";
import type { Metadata } from "next";

import { AskScreen } from "@/components/ask/ask-screen";

export const metadata: Metadata = { title: "Ask" };

export default async function Page({ params }: PageProps<"/w/[wid]/ask">) {
  const { wid } = await params;
  return (
    <Suspense>
      <AskScreen wid={wid} />
    </Suspense>
  );
}
