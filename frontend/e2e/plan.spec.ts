import { expect, expectToast, PLAN_B, test, waitForToastsToClear, WS_B } from "./fixtures";

test("plan review shows the request, the proposal and every section", async ({ page }) => {
  await page.goto(`/w/${WS_B}/plan/${PLAN_B}`);
  await expect(page.getByRole("heading", { level: 1, name: "Review the monitoring plan" })).toBeVisible();
  await expect(page.getByRole("figure", { name: "You asked" })).toContainText("Monitor Stripe's pricing and product launches");

  const sections = page.getByRole("navigation", { name: "Plan sections" });
  for (const section of ["Entities", "Areas", "Tracked values", "Sources"]) {
    await expect(sections.getByRole("link", { name: section })).toBeVisible();
  }
  await expect(page.getByRole("region", { name: "Questions from the planner" })).toBeVisible();
  await expect(page.getByRole("switch", { name: "Monitor Stripe", exact: true })).toBeChecked();

  // Nothing is monitored until a human approves: both decisions are offered.
  await expect(page.getByRole("button", { name: "Approve & start monitoring" })).toBeEnabled();
  await expect(page.getByRole("button", { name: "Reject" })).toBeEnabled();
});

test("onboarding → planner → plan review → approve starts monitoring", async ({ page }) => {
  // The mock planner takes ~20 s, and the new workspace then builds its baseline.
  test.setTimeout(120_000);
  const subject = `Acme Test ${Date.now().toString(36)}`;

  await page.goto("/new");
  await expect(page.getByRole("heading", { level: 1, name: "About your company" })).toBeVisible();
  await page.getByRole("button", { name: "Continue" }).click();

  await page.getByLabel("Monitoring request").fill(`I want to monitor ${subject}`);
  await expect(page.getByText(`“${subject}”`)).toBeVisible(); // derived workspace name
  await page.getByRole("button", { name: "Start research" }).click();

  await expect(page).toHaveURL(/\/w\/[0-9a-f-]+\/plan\/[0-9a-f-]+$/);
  await expect(page.getByRole("heading", { level: 1, name: "Researching your request" })).toBeVisible();

  // The live planner view turns into the review once the plan is ready.
  await expect(page.getByRole("heading", { level: 1, name: "Review the monitoring plan" })).toBeVisible({
    timeout: 60_000,
  });
  // A "plan is ready" toast covers the sticky action bar's corner until it times out.
  await waitForToastsToClear(page);
  await page.getByRole("button", { name: "Approve & start monitoring" }).click();

  await expectToast(page, "Monitoring started");
  await expect(page).toHaveURL(/\/w\/[0-9a-f-]+$/);
  await expect(page.getByRole("heading", { level: 1, name: subject })).toBeVisible();
});
