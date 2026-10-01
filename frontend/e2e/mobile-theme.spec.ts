import type { Page } from "@playwright/test";

import { expect, HEADLINE_REPORT, test, WS_A } from "./fixtures";

async function expectNoHorizontalScroll(page: Page) {
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow, "page should not scroll horizontally").toBeLessThanOrEqual(1);
}

test.describe("mobile (375 px)", () => {
  test.use({ viewport: { width: 375, height: 812 }, hasTouch: true, isMobile: true });

  test("dashboard fits the screen and navigation opens as a sheet", async ({ page }) => {
    await page.goto(`/w/${WS_A}`);
    await expect(page.getByRole("heading", { level: 1, name: "Razorpay watch" })).toBeVisible();
    await expect(page.getByRole("region", { name: "What you're monitoring" })).toBeVisible();
    await expect(page.getByRole("list", { name: /Attention funnel/ })).toBeAttached();
    await expectNoHorizontalScroll(page);

    // The sidebar is hidden below 768 px and opens as a sheet.
    await expect(page.getByRole("navigation", { name: "Workspace" })).toBeHidden();
    await page.getByRole("button", { name: "Toggle navigation" }).click();
    const sheet = page.getByRole("dialog");
    await expect(sheet.getByRole("navigation", { name: "Workspace" })).toBeVisible();
    await sheet.getByRole("link", { name: /^Intelligence/ }).click();
    await expect(page).toHaveURL(new RegExp(`/w/${WS_A}/intel`));
    await expect(page.getByRole("heading", { level: 1, name: "Intelligence" })).toBeVisible();
  });

  test("intelligence card is readable", async ({ page }) => {
    await page.goto(`/w/${WS_A}/intel/${HEADLINE_REPORT}`);
    await expect(page.getByRole("heading", { level: 1, name: /Razorpay introduces 0% platform fee/ })).toBeVisible();
    await expect(page.getByRole("region", { name: "What changed" })).toBeVisible();
    const evidence = page.getByRole("region", { name: "Evidence" });
    await evidence.scrollIntoViewIfNeeded();
    await expect(evidence.locator("blockquote").first()).toBeVisible();
    await expectNoHorizontalScroll(page);
  });
});

test("dark mode toggle applies and persists", async ({ page }) => {
  await page.goto(`/w/${WS_A}`);
  const html = page.locator("html");

  await page.getByRole("button", { name: "Change theme" }).first().click();
  await page.getByRole("menuitemradio", { name: "Dark" }).click();
  await expect(html).toHaveClass(/\bdark\b/);
  const darkBackground = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);

  await page.reload();
  await expect(html).toHaveClass(/\bdark\b/);

  await page.getByRole("button", { name: "Change theme" }).first().click();
  await page.getByRole("menuitemradio", { name: "Light" }).click();
  await expect(html).not.toHaveClass(/\bdark\b/);
  const lightBackground = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);
  expect(lightBackground).not.toBe(darkBackground);
});
