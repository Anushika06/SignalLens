import { expect, test, WS_A } from "./fixtures";

test("workspace list opens the workspace dashboard", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1, name: "Workspaces" })).toBeVisible();
  await expect(page.getByRole("link", { name: "New workspace" })).toBeVisible();

  const workspace = page.getByRole("link", { name: /Razorpay watch/ });
  await expect(workspace).toBeVisible();
  await workspace.click();

  await expect(page).toHaveURL(new RegExp(`/w/${WS_A}$`));
  await expect(page.getByRole("heading", { level: 1, name: "Razorpay watch" })).toBeVisible();
});

test("dashboard shows subjects, intelligence, the attention funnel and live activity", async ({ page }) => {
  await page.goto(`/w/${WS_A}`);
  const main = page.getByRole("main");

  // Subjects
  const subjects = main.getByRole("region", { name: "What you're monitoring" });
  await expect(subjects).toBeVisible();
  await expect(subjects.getByRole("link", { name: "Razorpay" })).toHaveAttribute("href", /\/world\//);

  // Intelligence with severity and evidence as separate, text-labelled badges
  const headline = main.getByRole("link", { name: /Razorpay introduces 0% platform fee/ }).first();
  await expect(headline).toBeVisible();
  await expect(main.getByText("High severity").first()).toBeAttached();

  // Attention funnel: checks headline + the stages
  const funnel = main.getByRole("list", { name: /Attention funnel/ });
  await expect(funnel).toBeVisible();
  for (const stage of ["Changes", "Filtered out", "Material", "Investigated", "Published"]) {
    await expect(funnel.getByText(stage, { exact: false })).toBeVisible();
  }
  await expect(main.getByText(/checks of pages and news feeds/)).toBeVisible();

  // Agent activity feed
  await expect(main.getByText("Agent activity")).toBeVisible();
  await expect(main.getByRole("link", { name: /^(Checked|Investigating|Published)/ }).first()).toBeVisible();
  await expect(main.getByRole("link", { name: "All agent runs" })).toBeVisible();

  // Sidebar navigation reaches every workspace screen
  const nav = page.getByRole("navigation", { name: "Workspace" });
  for (const item of ["Dashboard", "Intelligence", "World state", "Monitoring", "Agent runs", "Approvals", "Settings"]) {
    await expect(nav.getByRole("link", { name: new RegExp(`^${item}`) })).toBeVisible();
  }
});

test("pending approvals callout links to the approvals page", async ({ page }) => {
  await page.goto(`/w/${WS_A}`);
  const callout = page.getByRole("status").filter({ hasText: /waiting for your decision/ });
  await expect(callout).toBeVisible();
  await callout.getByRole("link", { name: "Review" }).click();
  await expect(page).toHaveURL(new RegExp(`/w/${WS_A}/approvals$`));
  await expect(page.getByRole("heading", { level: 1, name: "Approvals" })).toBeVisible();
});

test("agent runs list opens a run trace", async ({ page }) => {
  await page.goto(`/w/${WS_A}/runs`);
  await expect(page.getByRole("heading", { level: 1, name: "Agent runs" })).toBeVisible();
  const runLink = page.getByRole("table").getByRole("link").first();
  await expect(runLink).toHaveAttribute("href", new RegExp(`/w/${WS_A}/runs/`));
  await runLink.click();
  await expect(page).toHaveURL(new RegExp(`/w/${WS_A}/runs/[0-9a-f-]+$`));
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
});
