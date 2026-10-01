"use client";

import { useState } from "react";
import Link from "next/link";
import { Bell, CheckCheck } from "lucide-react";
import { toast } from "sonner";
import { mutate } from "swr";

import { SeverityDot } from "@/components/common/badges";
import { RelativeTime } from "@/components/common/relative-time";
import { errorMessage } from "@/components/common/states";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Skeleton } from "@/components/ui/skeleton";
import { api, paths } from "@/lib/api";
import { NOTIFICATIONS_LIMIT, useUnreadNotifications } from "@/lib/hooks";
import { NOTIFICATION_CHANNEL } from "@/lib/labels";
import { routes } from "@/lib/routes";

/**
 * Inbox of unread notifications (intelligence routed to your teams). Opening a notification
 * opens its report; "Mark all as read" clears the inbox.
 */
export function NotificationsBell({ wid }: { wid: string }) {
  const [open, setOpen] = useState(false);
  const [clearing, setClearing] = useState(false);
  const { data, isLoading } = useUnreadNotifications(wid);
  const unread = data ?? [];
  const count = unread.length;
  const countLabel = count >= NOTIFICATIONS_LIMIT ? `${NOTIFICATIONS_LIMIT}+` : String(count);

  async function markAllRead() {
    setClearing(true);
    try {
      await api.notifications.readAll(wid);
      await mutate(paths.notifications(wid, { unread: true, limit: NOTIFICATIONS_LIMIT }), []);
    } catch (error) {
      toast.error("Couldn't mark notifications as read", { description: errorMessage(error) });
    } finally {
      setClearing(false);
    }
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          variant="ghost"
          size="icon"
          className="relative"
          aria-label={count ? `Notifications, ${countLabel} unread` : "Notifications"}
        >
          <Bell aria-hidden="true" />
          {count > 0 ? (
            <span
              aria-hidden="true"
              className="metric absolute -top-0.5 -right-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-primary px-1 text-[10px] leading-none font-semibold text-primary-foreground ring-2 ring-background"
            >
              {countLabel}
            </span>
          ) : null}
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-[min(92vw,380px)] gap-0 p-0">
        <div className="flex items-center justify-between gap-2 border-b px-3 py-2.5">
          <p className="text-sm font-medium">Notifications</p>
          {count > 0 ? (
            <Button variant="ghost" size="xs" onClick={markAllRead} disabled={clearing}>
              <CheckCheck aria-hidden="true" />
              Mark all as read
            </Button>
          ) : null}
        </div>
        <div className="max-h-[min(60vh,420px)] overflow-y-auto">
          {isLoading ? (
            <div className="space-y-3 p-3">
              <Skeleton className="h-10 w-full" />
              <Skeleton className="h-10 w-full" />
            </div>
          ) : count === 0 ? (
            <div className="px-4 py-8 text-center">
              <p className="text-sm font-medium">You&apos;re all caught up</p>
              <p className="mt-1 text-xs text-pretty text-muted-foreground">
                Critical and high-severity intelligence routed to your teams shows up here. Everything else goes to the
                daily digest.
              </p>
            </div>
          ) : (
            <ul className="divide-y">
              {unread.map((item) => (
                <li key={item.id}>
                  <Link
                    href={routes.report(wid, item.report_id)}
                    onClick={() => setOpen(false)}
                    className="flex gap-3 px-3 py-2.5 transition-colors hover:bg-muted/60 focus-visible:bg-muted/60 focus-visible:outline-none"
                  >
                    <SeverityDot severity={item.severity} className="mt-1.5" />
                    <span className="min-w-0 flex-1">
                      <span className="line-clamp-2 text-sm leading-snug">{item.title}</span>
                      <span className="mt-0.5 flex flex-wrap items-center gap-x-1.5 text-xs text-muted-foreground">
                        {item.team ? <span>{item.team}</span> : null}
                        {item.team ? <span aria-hidden="true">·</span> : null}
                        <span>{NOTIFICATION_CHANNEL[item.channel]}</span>
                        <span aria-hidden="true">·</span>
                        <RelativeTime value={item.created_at} />
                      </span>
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </div>
        <div className="border-t p-1.5">
          <Button asChild variant="ghost" size="sm" className="w-full">
            <Link href={routes.intel(wid)} onClick={() => setOpen(false)}>
              Open the intelligence feed
            </Link>
          </Button>
        </div>
      </PopoverContent>
    </Popover>
  );
}
