import type { Page } from "@playwright/test";

import { expect, HEADLINE_REPORT, test, WS_A } from "./fixtures";

/** The feed's filter selects show "Severity: Any", "Evidence: Confirmed", … as their text. */
function filter(page: Page, label: string) {
  return page.getByRole("group", { name: "Filter reports" }).getByRole("combobox").filter({ hasText: `${label}:` });
}

test.describe("intelligence feed", () => {
  test("filters by severity and evidence and switches between live and historical", async ({ page }) => {
    await page.goto(`/w/${WS_A}/intel`);
    await expect(page.getByRole("heading", { level: 1, name: "Intelligence" })).toBeVisible();
    const reports = page.getByRole("region", { name: "Reports" });
    const items = reports.getByRole("listitem");
    await expect(items.first()).toBeVisible();
    const total = await items.count();
    expect(total).toBeGreaterThan(1);

    // Severity filter → URL query + only high-severity cards
    await filter(page, "Severity").click();
    await page.getByRole("option", { name: "High", exact: true }).click();
    await expect(page).toHaveURL(/severity=high/);
    await expect(filter(page, "Severity")).toContainText("High");
    await expect(items.first()).toBeVisible();
    await expect.poll(() => items.count()).toBeLessThan(total);
    for (const item of await items.all()) {
      await expect(item.getByText("High severity")).toBeAttached();
    }

    // Reset severity, filter by evidence status instead
    await filter(page, "Severity").click();
    await page.getByRole("option", { name: "Any", exact: true }).click();
    await expect(page).not.toHaveURL(/severity=/);

    await filter(page, "Evidence").click();
    await page.getByRole("option", { name: "Confirmed", exact: true }).click();
    await expect(page).toHaveURL(/evidence=confirmed/);
    await expect(items.first()).toBeVisible();
    for (const item of await items.all()) {
      await expect(item.getByText("Confirmed", { exact: true }).first()).toBeVisible();
    }

    // Historical (web-archive backfill) view
    await filter(page, "Evidence").click();
    await page.getByRole("option", { name: "Any", exact: true }).click();
    await page.getByRole("radio", { name: "Historical" }).click();
    await expect(page).toHaveURL(/view=historical/);
    await expect(page.getByRole("radio", { name: "Historical" })).toBeChecked();
    await expect(items.first()).toBeVisible();
    await expect(reports.getByText("Historical").first()).toBeVisible();
  });

  test("opens a card from the feed", async ({ page }) => {
    await page.goto(`/w/${WS_A}/intel`);
    await page.getByRole("link", { name: /Razorpay introduces 0% platform fee/ }).click();
    await expect(page).toHaveURL(new RegExp(`/intel/${HEADLINE_REPORT}$`));
    await expect(page.getByRole("heading", { level: 1, name: /Razorpay introduces 0% platform fee/ })).toBeVisible();
  });
});

test.describe("intelligence card", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(`/w/${WS_A}/intel/${HEADLINE_REPORT}`);
    await expect(page.getByRole("heading", { level: 1, name: /Razorpay introduces 0% platform fee/ })).toBeVisible();
  });

  test("separates facts from the agent's assessment", async ({ page }) => {
    const card = page.getByRole("article").first();
    await expect(card.getByText("High severity").first()).toBeAttached();
    await expect(card.getByText("Confirmed").first()).toBeVisible();

    const facts = page.getByRole("region", { name: "What changed" });
    await expect(facts.getByText(/Facts only/)).toBeVisible();
    await expect(facts.getByRole("deletion")).toContainText("2% flat");
    await expect(facts.getByRole("insertion")).toContainText("0% for the first 90 days");

    const assessment = page.getByRole("region", { name: "Why it matters to you" });
    await expect(assessment.getByText(/Agent assessment/)).toBeVisible();
    await expect(assessment.getByRole("heading", { name: "Assumptions" })).toBeVisible();
    await expect(assessment.getByRole("list", { name: "Affected teams" })).toBeVisible();
  });

  test("shows evidence with verified quotes and source links", async ({ page }) => {
    const evidence = page.getByRole("region", { name: "Evidence" });
    const items = evidence.getByRole("list", { name: "Evidence items" }).getByRole("listitem");
    await expect(items.first()).toBeVisible();
    expect(await items.count()).toBeGreaterThanOrEqual(2);

    const primary = items.first();
    await expect(primary.locator("blockquote")).toContainText("0% platform fee");
    await expect(primary.getByText("Quote verified")).toBeVisible();
    const sourceLink = primary.getByRole("link", { name: /opens in a new tab/ });
    await expect(sourceLink).toHaveAttribute("href", /^https:\/\//);
    await expect(sourceLink).toHaveAttribute("target", "_blank");
    await expect(sourceLink).toHaveAttribute("rel", /noopener/);

    await expect(evidence.getByRole("article", { name: /^Supports:/ }).first()).toBeVisible();
  });

  test("links to the investigation trace", async ({ page }) => {
    const investigation = page.getByRole("region", { name: "Investigation" });
    await expect(investigation.getByRole("heading", { name: "Conclusion" })).toBeVisible();
    await investigation.getByRole("link", { name: "Full run trace" }).click();
    await expect(page).toHaveURL(new RegExp(`/w/${WS_A}/runs/[0-9a-f-]+$`));
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  });
});
