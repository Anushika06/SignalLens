import { Suspense } from "react";
import type { Metadata } from "next";

import { DemoLabScreen } from "@/components/lab/demo-lab-screen";

export const metadata: Metadata = { title: "Demo lab" };

export default function Page() {
  return (
    <Suspense>
      <DemoLabScreen />
    </Suspense>
  );
}
