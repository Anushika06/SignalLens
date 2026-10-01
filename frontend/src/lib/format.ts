/**
 * Formatting helpers. Dates arrive as ISO-8601 UTC strings and are shown in the viewer's
 * local time zone: relative in the UI ("12 min ago"), absolute in tooltips.
 */
import { differenceInSeconds, format, formatDistanceToNowStrict, isValid, parseISO } from "date-fns";

function toDate(value: string | Date): Date | null {
  const date = typeof value === "string" ? parseISO(value) : value;
  return isValid(date) ? date : null;
}

/** "just now", "12 min ago", "in 3 hours", "2 days ago". */
export function formatRelative(value: string | Date | null | undefined): string {
  if (!value) return "—";
  const date = toDate(value);
  if (!date) return "—";
  const seconds = differenceInSeconds(date, new Date());
  if (Math.abs(seconds) < 45) return seconds > 0 ? "in a moment" : "just now";
  return formatDistanceToNowStrict(date, { addSuffix: true })
    .replace(/ minutes?/, " min")
    .replace(/ seconds?/, " s");
}

/** "28 Sep 2026, 15:45" */
export function formatDateTime(value: string | Date | null | undefined): string {
  if (!value) return "—";
  const date = toDate(value);
  return date ? format(date, "d MMM yyyy, HH:mm") : "—";
}

/** "28 Sep 2026" */
export function formatDate(value: string | Date | null | undefined): string {
  if (!value) return "—";
  const date = toDate(value);
  return date ? format(date, "d MMM yyyy") : "—";
}

/** "Sep 2026" — for archive captures where the day is not meaningful. */
export function formatMonth(value: string | Date | null | undefined): string {
  if (!value) return "—";
  const date = toDate(value);
  return date ? format(date, "MMM yyyy") : "—";
}

const integer = new Intl.NumberFormat("en-US");
const compact = new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 });

/** 1,240 */
export function formatNumber(value: number | null | undefined): string {
  return value === null || value === undefined ? "—" : integer.format(value);
}

/** 12.4K */
export function formatCompact(value: number | null | undefined): string {
  return value === null || value === undefined ? "—" : compact.format(value);
}

/** 850 ms · 2.4 s · 1 min 12 s */
export function formatDuration(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return "—";
  if (ms < 1000) return `${Math.round(ms)} ms`;
  const seconds = ms / 1000;
  if (seconds < 60) return `${seconds.toFixed(seconds < 10 ? 1 : 0)} s`;
  const minutes = Math.floor(seconds / 60);
  const rest = Math.round(seconds % 60);
  return rest ? `${minutes} min ${rest} s` : `${minutes} min`;
}

/** Duration between two ISO timestamps (running runs measure against now). */
export function durationBetween(start: string | null, end: string | null): number | null {
  if (!start) return null;
  const from = toDate(start);
  const to = end ? toDate(end) : new Date();
  if (!from || !to) return null;
  return Math.max(0, to.getTime() - from.getTime());
}

/** $0.042 · <$0.01 · $1.20 */
export function formatUsd(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  if (value === 0) return "$0.00";
  if (value < 0.01) return "<$0.01";
  return `$${value.toFixed(value < 1 ? 3 : 2)}`;
}

/** Check frequencies offered when editing a plan or a source (hours). */
export const CHECK_INTERVAL_OPTIONS = [1, 3, 6, 12, 24, 48, 72, 168] as const;

/** 1 → "Hourly", 6 → "Every 6 h", 24 → "Daily", 72 → "Every 3 days", 168 → "Weekly". */
export function formatInterval(hours: number | null | undefined): string {
  if (hours === null || hours === undefined || !Number.isFinite(hours)) return "—";
  if (hours < 1) return `Every ${Math.round(hours * 60)} min`;
  if (hours === 1) return "Hourly";
  if (hours === 24) return "Daily";
  if (hours === 168) return "Weekly";
  if (hours % 24 === 0) return `Every ${hours / 24} days`;
  return `Every ${Number.isInteger(hours) ? hours : hours.toFixed(1)} h`;
}

/** "value_change" → "Value change" (fallback for enum-ish strings without a label). */
export function humanize(value: string): string {
  const text = value.replace(/[_.-]+/g, " ").trim();
  return text.charAt(0).toUpperCase() + text.slice(1);
}

/** "https://razorpay.com/pricing/" → "razorpay.com/pricing" */
export function prettyUrl(url: string | null | undefined): string {
  if (!url) return "";
  return url.replace(/^https?:\/\//, "").replace(/^www\./, "").replace(/\/$/, "");
}

/** "https://economictimes.indiatimes.com/x" → "economictimes.indiatimes.com" */
export function hostname(url: string | null | undefined): string {
  if (!url) return "";
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return prettyUrl(url).split("/")[0] ?? url;
  }
}

/** Pluralise: plural(3, "source") → "3 sources". */
export function plural(count: number, singular: string, pluralForm = `${singular}s`): string {
  return `${formatNumber(count)} ${count === 1 ? singular : pluralForm}`;
}
