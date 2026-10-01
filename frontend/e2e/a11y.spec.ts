import AxeBuilder from "@axe-core/playwright";
import type { Page, TestInfo } from "@playwright/test";

import { expect, HEADLINE_REPORT, SIGNED_OUT_ME, test, WS_A } from "./fixtures";

/**
 * Accessibility smoke test with axe-core (WCAG 2.1 A/AA rules).
 *
 * Policy: every serious and critical violation is reported (as a test annotation and a JSON
 * attachment in the HTML report), but only **critical** ones fail the test. Serious findings —
 * mostly colour contrast, which axe measures differently across fonts, anti-aliasing and
 * transient states such as toasts and skeletons — are tracked without making CI flaky.
 */
async function auditPage(page: Page, testInfo: TestInfo) {
  // Let skeletons resolve and enter animations finish before measuring.
  await page.waitForLoadState("networkidle");
  await page.waitForTimeout(500);

  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
    // Toasts come and go; they are not part of the page under test.
    .exclude("[data-sonner-toaster]")
    .analyze();

  const relevant = results.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
  const summary = relevant.map((v) => ({
    id: v.id,
    impact: v.impact,
    help: v.help,
    nodes: v.nodes.length,
    targets: v.nodes.slice(0, 5).map((n) => n.target.join(" ")),
  }));
  await testInfo.attach("axe-serious-and-critical.json", {
    body: JSON.stringify(summary, null, 2),
    contentType: "application/json",
  });
  for (const violation of summary) {
    testInfo.annotations.push({
      type: `a11y-${violation.impact}`,
      description: `${violation.id} (${violation.nodes} nodes): ${violation.help}`,
    });
  }

  const critical = summary.filter((v) => v.impact === "critical");
  expect(critical, "critical accessibility violations").toEqual([]);
}

test.describe("accessibility (axe), signed out", () => {
  test.use({ storageState: { cookies: [], origins: [] } });

  test("login page", async ({ page, health }, testInfo) => {
    health.allow(SIGNED_OUT_ME);
    await page.goto("/login");
    await expect(page.getByRole("button", { name: "Sign in", exact: true })).toBeVisible();
    await auditPage(page, testInfo);
  });
});

test.describe("accessibility (axe)", () => {
  test("workspace dashboard", async ({ page }, testInfo) => {
    await page.goto(`/w/${WS_A}`);
    await expect(page.getByRole("region", { name: "What you're monitoring" })).toBeVisible();
    await auditPage(page, testInfo);
  });

  test("intelligence card", async ({ page }, testInfo) => {
    await page.goto(`/w/${WS_A}/intel/${HEADLINE_REPORT}`);
    await expect(page.getByRole("region", { name: "Evidence" })).toBeVisible();
    await auditPage(page, testInfo);
  });
});
