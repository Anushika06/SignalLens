import type { Metadata } from "next";

import { WorkspaceListScreen } from "@/components/workspaces/workspace-list-screen";

export const metadata: Metadata = { title: "Workspaces" };

export default function Page() {
  return <WorkspaceListScreen />;
}
