import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  durationBetween,
  formatCompact,
  formatDate,
  formatDateTime,
  formatDuration,
  formatInterval,
  formatMonth,
  formatNumber,
  formatRelative,
  formatUsd,
  hostname,
  humanize,
  plural,
  prettyUrl,
} from "./format";

// Dates are built in local time so the assertions hold in every time zone.
const NOW = new Date(2026, 8, 28, 15, 45, 0);

describe("formatRelative", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(NOW);
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("returns a dash for empty or invalid input", () => {
    expect(formatRelative(null)).toBe("—");
    expect(formatRelative(undefined)).toBe("—");
    expect(formatRelative("")).toBe("—");
    expect(formatRelative("not a date")).toBe("—");
  });

  it("says 'just now' / 'in a moment' within 45 seconds", () => {
    expect(formatRelative(new Date(NOW.getTime() - 10_000))).toBe("just now");
    expect(formatRelative(new Date(NOW.getTime() + 10_000))).toBe("in a moment");
  });

  it("abbreviates minutes and keeps hours and days", () => {
    expect(formatRelative(new Date(NOW.getTime() - 12 * 60_000))).toBe("12 min ago");
    expect(formatRelative(new Date(NOW.getTime() - 60_000))).toBe("1 min ago");
    expect(formatRelative(new Date(NOW.getTime() + 3 * 3_600_000))).toBe("in 3 hours");
    expect(formatRelative(new Date(NOW.getTime() - 2 * 86_400_000))).toBe("2 days ago");
  });

  it("accepts ISO strings", () => {
    expect(formatRelative(new Date(NOW.getTime() - 5 * 60_000).toISOString())).toBe("5 min ago");
  });
});

describe("absolute dates", () => {
  it("formats date-times, dates and months", () => {
    expect(formatDateTime(NOW)).toBe("28 Sep 2026, 15:45");
    expect(formatDate(NOW)).toBe("28 Sep 2026");
    expect(formatMonth(NOW)).toBe("Sep 2026");
  });

  it("returns a dash for missing or invalid values", () => {
    for (const fn of [formatDateTime, formatDate, formatMonth]) {
      expect(fn(null)).toBe("—");
      expect(fn(undefined)).toBe("—");
      expect(fn("garbage")).toBe("—");
    }
  });
});

describe("numbers", () => {
  it("formats integers with separators", () => {
    expect(formatNumber(1240)).toBe("1,240");
    expect(formatNumber(0)).toBe("0");
    expect(formatNumber(null)).toBe("—");
  });

  it("formats compact numbers", () => {
    expect(formatCompact(12_400)).toBe("12.4K");
    expect(formatCompact(999)).toBe("999");
    expect(formatCompact(undefined)).toBe("—");
  });

  it("formats USD costs", () => {
    expect(formatUsd(0)).toBe("$0.00");
    expect(formatUsd(0.004)).toBe("<$0.01");
    expect(formatUsd(0.042)).toBe("$0.042");
    expect(formatUsd(1.2)).toBe("$1.20");
    expect(formatUsd(null)).toBe("—");
  });

  it("pluralises", () => {
    expect(plural(1, "source")).toBe("1 source");
    expect(plural(3, "source")).toBe("3 sources");
    expect(plural(0, "entity", "entities")).toBe("0 entities");
    expect(plural(1200, "check")).toBe("1,200 checks");
  });
});

describe("durations", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it("formats milliseconds, seconds and minutes", () => {
    expect(formatDuration(850)).toBe("850 ms");
    expect(formatDuration(2400)).toBe("2.4 s");
    expect(formatDuration(42_000)).toBe("42 s");
    expect(formatDuration(72_000)).toBe("1 min 12 s");
    expect(formatDuration(120_000)).toBe("2 min");
    expect(formatDuration(null)).toBe("—");
  });

  it("measures between timestamps, never negative", () => {
    const start = "2026-09-28T10:00:00Z";
    expect(durationBetween(start, "2026-09-28T10:00:05Z")).toBe(5000);
    expect(durationBetween("2026-09-28T10:00:05Z", start)).toBe(0);
    expect(durationBetween(null, start)).toBeNull();
    expect(durationBetween("bad", start)).toBeNull();
  });

  it("measures running durations against now", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-09-28T10:01:00Z"));
    expect(durationBetween("2026-09-28T10:00:00Z", null)).toBe(60_000);
  });
});

describe("formatInterval", () => {
  it.each([
    [0.5, "Every 30 min"],
    [1, "Hourly"],
    [6, "Every 6 h"],
    [1.5, "Every 1.5 h"],
    [24, "Daily"],
    [72, "Every 3 days"],
    [168, "Weekly"],
  ])("%s hours -> %s", (hours, expected) => {
    expect(formatInterval(hours)).toBe(expected);
  });

  it("returns a dash for missing or non-finite values", () => {
    expect(formatInterval(null)).toBe("—");
    expect(formatInterval(Number.NaN)).toBe("—");
    expect(formatInterval(Number.POSITIVE_INFINITY)).toBe("—");
  });
});

describe("text helpers", () => {
  it("humanizes enum-ish strings", () => {
    expect(humanize("value_change")).toBe("Value change");
    expect(humanize("api.rate-limit")).toBe("Api rate limit");
  });

  it("prettifies URLs", () => {
    expect(prettyUrl("https://razorpay.com/pricing/")).toBe("razorpay.com/pricing");
    expect(prettyUrl("http://www.example.com")).toBe("example.com");
    expect(prettyUrl(null)).toBe("");
  });

  it("extracts hostnames", () => {
    expect(hostname("https://economictimes.indiatimes.com/x")).toBe("economictimes.indiatimes.com");
    expect(hostname("https://www.rbi.org.in/notice")).toBe("rbi.org.in");
    expect(hostname("razorpay.com/pricing")).toBe("razorpay.com");
    expect(hostname(undefined)).toBe("");
  });
});
