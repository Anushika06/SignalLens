import { cookies } from "next/headers";

import { WorkspaceShell } from "@/components/shell/workspace-shell";

export default async function WorkspaceLayout({ children, params }: LayoutProps<"/w/[wid]">) {
  const { wid } = await params;
  // The sidebar remembers whether it was collapsed (cookie written by the sidebar component).
  const sidebarOpen = (await cookies()).get("sidebar_state")?.value !== "false";
  return (
    <WorkspaceShell wid={wid} sidebarOpen={sidebarOpen}>
      {children}
    </WorkspaceShell>
  );
}
