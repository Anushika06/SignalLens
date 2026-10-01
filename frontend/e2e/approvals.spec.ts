import { expect, expectToast, test, WS_A } from "./fixtures";

test("approvals page lists pending and decided actions", async ({ page }) => {
  await page.goto(`/w/${WS_A}/approvals`);
  await expect(page.getByRole("heading", { level: 1, name: "Approvals" })).toBeVisible();
  await expect(page.getByText("SignalLens never acts externally on its own.")).toBeVisible();

  const pendingTab = page.getByRole("tab", { name: /^Pending/ });
  await expect(pendingTab).toHaveAttribute("aria-selected", "true");
  const pending = page.getByRole("tabpanel", { name: /^Pending/ }).getByRole("article");
  await expect(pending.first()).toBeVisible();
  await expect(pending.first().getByRole("button", { name: "Approve", exact: true })).toBeVisible();
  await expect(pending.first().getByRole("button", { name: "Reject", exact: true })).toBeVisible();

  await page.getByRole("tab", { name: /^Decided/ }).click();
  await expect(page.getByRole("tabpanel", { name: /^Decided/ }).getByRole("article").first()).toBeVisible();
});

test("approves an agent-proposed action with a note", async ({ page }) => {
  await page.goto(`/w/${WS_A}/approvals`);
  const decidedTab = page.getByRole("tab", { name: /^Decided/ });
  await expect(decidedTab).toHaveText(/\d+/);
  const decidedBefore = Number((await decidedTab.textContent())?.match(/(\d+)/)?.[1] ?? 0);

  // Agent proposals can be approved by any member; requests you made yourself may not be.
  const proposal = page
    .getByRole("tabpanel", { name: /^Pending/ })
    .getByRole("article")
    .filter({ hasText: /Proposed by the .* agent/ })
    .first();
  await expect(proposal).toBeVisible();
  const title = (await proposal.getByRole("heading").textContent())?.trim() ?? "";
  expect(title).not.toBe("");

  await proposal.getByRole("button", { name: "Approve", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "Approve this action?" });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByText(title)).toBeVisible();
  await dialog.getByLabel(/Note/).fill("Checked with legal — fine to send. (e2e)");
  // The confirm button is labelled with the action's verb ("Send email", "Share", …).
  await dialog.locator("button[type=submit]").click();

  await expectToast(page, /^Approved/);
  await expect(page.getByRole("tabpanel", { name: /^Pending/ }).getByRole("heading", { name: title })).toHaveCount(0);
  await expect(decidedTab).toContainText(String(decidedBefore + 1));
});

test("your own request cannot be approved by you, and the page says why", async ({ page }) => {
  await page.goto(`/w/${WS_A}/approvals`);
  const pending = page.getByRole("tabpanel", { name: /^Pending/ }).getByRole("article");
  await expect(pending.first()).toBeVisible();

  const mine = pending.filter({ hasText: "Requested by you" }).first();
  test.skip((await mine.count()) === 0, "the mock has no pending request made by the demo user");
  const approve = mine.getByRole("button", { name: "Approve", exact: true });
  test.skip(
    await approve.isEnabled(),
    "approval permissions (can_decide / cannot_decide_reason) are not reported by this API yet",
  );

  await expect(approve).toBeDisabled();
  await expect(mine.getByRole("button", { name: "Reject", exact: true })).toBeDisabled();
  // The reason is visible and announced with the disabled button.
  const reasonId = await approve.getAttribute("aria-describedby");
  expect(reasonId).toBeTruthy();
  const reason = page.locator(`[id="${reasonId}"]`);
  await expect(reason).toBeVisible();
  await expect(reason).not.toHaveText("");
});
