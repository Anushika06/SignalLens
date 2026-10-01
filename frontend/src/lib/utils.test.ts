import { describe, expect, it } from "vitest";

import { safeNextPath } from "@/components/auth/safe-next";
import { safeHref } from "@/components/common/links";
import { deriveWorkspaceName } from "@/components/onboarding/derive-name";

import { cn } from "./utils";

describe("cn", () => {
  it("joins truthy class names", () => {
    expect(cn("a", false, null, undefined, "b")).toBe("a b");
  });

  it("lets later Tailwind utilities win", () => {
    expect(cn("px-2 text-sm", "px-4")).toBe("text-sm px-4");
    expect(cn("bg-red-50", { "bg-blue-50": true })).toBe("bg-blue-50");
  });
});

describe("safeHref", () => {
  it("allows only http(s) URLs", () => {
    expect(safeHref("https://razorpay.com/pricing")).toBe("https://razorpay.com/pricing");
    expect(safeHref("http://example.com")).toBe("http://example.com/");
    expect(safeHref("javascript:alert(1)")).toBeNull();
    expect(safeHref("data:text/html,hi")).toBeNull();
    expect(safeHref("/relative")).toBeNull();
    expect(safeHref(null)).toBeNull();
  });
});

describe("safeNextPath", () => {
  it("keeps same-origin relative paths", () => {
    expect(safeNextPath("/w/1/intel?view=all")).toBe("/w/1/intel?view=all");
  });

  it("rejects open redirects and the login page", () => {
    expect(safeNextPath(null)).toBe("/");
    expect(safeNextPath("https://evil.example")).toBe("/");
    expect(safeNextPath("//evil.example")).toBe("/");
    expect(safeNextPath("/\\evil.example")).toBe("/");
    expect(safeNextPath("/w/1\n")).toBe("/w/1");
    expect(safeNextPath("/a\u0000b")).toBe("/");
    expect(safeNextPath("/login")).toBe("/");
    expect(safeNextPath("/login?next=/x")).toBe("/");
    expect(safeNextPath("/loginx")).toBe("/loginx");
  });
});

describe("deriveWorkspaceName", () => {
  it.each([
    ["I want to monitor Razorpay", "Razorpay"],
    ["Monitor Tata Motors' EV business", "Tata Motors"],
    ["Monitor Pfizer's pipeline and regulatory approvals", "Pfizer"],
    ["track stripe pricing, launches", "Stripe pricing"],
    ["watch the RBI for payment rules", "RBI"],
    ["   ", ""],
  ])("%j -> %j", (request, expected) => {
    expect(deriveWorkspaceName(request)).toBe(expected);
  });
});
