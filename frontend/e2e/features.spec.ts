import { expect, expectToast, SIGNED_OUT_API, SIGNED_OUT_ME, test, WS_A } from "./fixtures";

/**
 * Journeys for features that are newer than the rest of the suite (SSO sign-in, members and
 * roles, team email recipients, the Ask page). Each one skips itself, with a reason, when the
 * build or the mock API does not offer the feature, so the suite stays green while they land.
 */

test.describe("single sign-on", () => {
  test.use({ storageState: { cookies: [], origins: [] } });

  test("signs in with the SSO button", async ({ page, health }) => {
    health.allow(SIGNED_OUT_ME);
    health.allow(SIGNED_OUT_API);
    const config = await page.request.get("/api/auth/sso/config");
    const sso = config.ok() ? ((await config.json()) as { enabled?: boolean; provider_name?: string }) : null;
    test.skip(!sso?.enabled, "the API reports single sign-on as disabled or does not support it");

    await page.goto("/login");
    const button = page.getByRole("link", { name: new RegExp(`^Continue with ${sso?.provider_name ?? ""}`) });
    await expect(button).toBeVisible();
    await button.click();

    await expect(page).toHaveURL(/\/$/);
    await expect(page.getByRole("heading", { level: 1, name: "Workspaces" })).toBeVisible();
  });
});

test.describe("members and roles", () => {
  test("settings lists the workspace members with their roles", async ({ page }) => {
    await page.goto(`/w/${WS_A}/settings`);
    await expect(page.getByRole("heading", { level: 1, name: "Settings" })).toBeVisible();
    const section = page.getByRole("region", { name: "Members & roles" });
    test.skip((await section.count()) === 0, "this build has no members settings");

    const members = section.getByRole("list", { name: "Workspace members" }).getByRole("listitem");
    await expect(members.first()).toBeVisible();
    await expect(section.getByText("demo@signallens.app")).toBeVisible();
    await expect(section.getByText(/Owner/).first()).toBeVisible();
  });
});

test.describe("team email recipients", () => {
  test("a team can have email recipients", async ({ page }) => {
    await page.goto(`/w/${WS_A}/settings`);
    const teams = page.getByRole("region", { name: "Teams" });
    await teams.getByRole("button", { name: "Edit" }).first().click();
    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible();
    const email = dialog.getByRole("textbox", { name: /email/i });
    test.skip((await email.count()) === 0, "this build has no email recipients on teams");

    const address = `e2e-${Date.now().toString(36)}@kivo.example`;
    await email.first().fill(address);
    await email.first().press("Enter");
    await dialog.locator("button[type=submit]").click();
    await expectToast(page, /^Saved/);
    await expect(teams.getByText(address)).toBeVisible();
  });
});

test.describe("ask", () => {
  test("asks a question and gets an answer with citations", async ({ page }) => {
    // Agent answers take a few seconds in the mock.
    test.setTimeout(90_000);
    const route = await page.request.get(`/w/${WS_A}/ask`);
    test.skip(route.status() === 404, "this build has no Ask page");
    const api = await page.request.get(`/api/workspaces/${WS_A}/ask?limit=1`);
    test.skip(!api.ok(), "the API does not implement Ask yet");

    await page.goto(`/w/${WS_A}/ask`);
    await expect(page.getByRole("heading", { level: 1, name: "Ask SignalLens" })).toBeVisible();
    const question = `What did Razorpay change in its pricing? (${Date.now().toString(36)})`;
    await page.getByLabel("Your question").fill(question);
    await page.getByRole("button", { name: "Ask", exact: true }).click();

    const thread = page.getByRole("region", { name: "Questions and answers" });
    const answer = thread.getByRole("article").filter({ hasText: question }).first();
    await expect(answer).toBeVisible();
    // The finished answer lists its numbered sources (facts, cards or web pages).
    const sources = answer.getByRole("list", { name: "Sources" });
    await expect(sources).toBeVisible({ timeout: 60_000 });
    await expect(sources.getByRole("listitem").first()).toBeVisible();
    await expect(answer).toHaveAttribute("aria-busy", "false");
  });
});
