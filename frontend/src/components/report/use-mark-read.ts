"use client";

import { useEffect, useRef } from "react";

import { api, paths } from "@/lib/api";
import { revalidate } from "@/lib/hooks";
import type { ReportDetail } from "@/lib/types";

/**
 * Opening a card marks it read (POST /reports/{rid}/read) once per open. When it was unread,
 * every workspace counter that depends on it (sidebar badge, bell, lists) is refreshed.
 * The ref guard keeps React StrictMode's double effect from sending it twice.
 */
export function useMarkRead(wid: string, report: ReportDetail | undefined) {
  const handled = useRef<string | null>(null);

  useEffect(() => {
    if (!report || handled.current === report.id) return;
    handled.current = report.id;
    const wasUnread = report.unread;
    api.reports.markRead(wid, report.id).then(
      () => {
        void revalidate(wasUnread ? paths.workspace(wid) : paths.notifications(wid));
      },
      () => {
        // Not worth interrupting the reader; try again the next time the report reloads.
        handled.current = null;
      },
    );
  }, [wid, report]);
}
