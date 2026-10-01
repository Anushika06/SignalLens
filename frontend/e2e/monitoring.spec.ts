import { expect, expectToast, test, WS_A } from "./fixtures";

test("sources tab lists sources with health and actions", async ({ page }) => {
  await page.goto(`/w/${WS_A}/monitoring`);
  await expect(page.getByRole("heading", { level: 1, name: "Monitoring" })).toBeVisible();
  await expect(page.getByRole("region", { name: "Active monitoring plan" })).toBeVisible();

  await expect(page.getByRole("tab", { name: /^Sources/ })).toHaveAttribute("aria-selected", "true");
  const table = page.getByRole("tabpanel", { name: /^Sources/ }).getByRole("table");
  await expect(table.getByRole("columnheader", { name: "Last check" })).toBeVisible();
  const rows = table.getByRole("rowgroup").nth(1).getByRole("row");
  await expect(rows.first()).toBeVisible();
  expect(await rows.count()).toBeGreaterThan(3);

  // Expand a source to see its recent checks, then trigger a manual check.
  await rows.first().getByRole("button", { name: /^Show details for/ }).click();
  await expect(page.getByText(/Recent checks/i).first()).toBeVisible();
  await rows.first().getByRole("button", { name: "Check now" }).click();
  await expectToast(page, /check/i);
});

test("learned rules can be undone", async ({ page }) => {
  await page.goto(`/w/${WS_A}/monitoring?tab=rules`);
  const panel = page.getByRole("tabpanel", { name: /^Learned rules/ });
  await expect(panel.getByText(/every change is visible and reversible/)).toBeVisible();

  const undoneToggle = panel.getByRole("button", { name: /^Undone rules/ });
  const undoneBefore = Number((await undoneToggle.textContent())?.match(/\((\d+)\)/)?.[1] ?? 0);
  const undoButtons = panel.getByRole("button", { name: "Undo", exact: true });
  const activeBefore = await undoButtons.count();
  expect(activeBefore, "the mock has active learned rules to undo").toBeGreaterThan(0);

  await undoButtons.first().click();
  const confirm = page.getByRole("alertdialog", { name: "Undo this learned rule?" });
  await expect(confirm).toBeVisible();
  await confirm.getByRole("button", { name: "Undo rule" }).click();

  await expectToast(page, "Rule undone");
  await expect(undoButtons).toHaveCount(activeBefore - 1);
  await expect(undoneToggle).toContainText(`(${undoneBefore + 1})`);
});

test("filtered changes explain what was ignored", async ({ page }) => {
  await page.goto(`/w/${WS_A}/monitoring?tab=filtered`);
  const panel = page.getByRole("tabpanel", { name: /^Filtered changes/ });
  await expect(panel).toBeVisible();
  await expect(panel.getByText(/Tier [012]/).first()).toBeVisible();
});
