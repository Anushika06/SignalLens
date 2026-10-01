import { DEMO, expect, SIGNED_OUT_API, SIGNED_OUT_ME, test, WS_A } from "./fixtures";

// These tests manage their own session: signing out must not end the shared one.
test.use({ storageState: { cookies: [], origins: [] } });

test.describe("authentication", () => {
  test.beforeEach(({ health }) => {
    health.allow(SIGNED_OUT_ME);
    // Protected pages discover a missing session through 401s, then redirect to /login.
    health.allow(SIGNED_OUT_API);
  });

  test("signs in with the demo account and signs out", async ({ page }) => {
    await page.goto("/login");
    await expect(page.getByRole("heading", { level: 1, name: "Welcome to SignalLens" })).toBeVisible();

    // The demo shortcut is shown when the backend allows the demo login; otherwise type it.
    const shortcut = page.getByRole("button", { name: "Use the demo account" });
    if (await shortcut.isVisible()) {
      await shortcut.click();
      await expect(page.getByLabel("Work email")).toHaveValue(DEMO.email);
    } else {
      await page.getByLabel("Work email").fill(DEMO.email);
      await page.getByLabel("Password").fill(DEMO.password);
    }
    await page.getByRole("button", { name: "Sign in", exact: true }).click();

    await expect(page).toHaveURL(/\/$/);
    await expect(page.getByRole("heading", { level: 1, name: "Workspaces" })).toBeVisible();

    await page.getByRole("button", { name: "Account menu" }).click();
    const menu = page.getByRole("menu");
    await expect(menu.getByText(DEMO.email)).toBeVisible();
    await menu.getByRole("menuitem", { name: "Log out" }).click();

    await expect(page).toHaveURL(/\/login/);
    await expect(page.getByRole("button", { name: "Sign in", exact: true })).toBeVisible();

    // The session is gone: protected pages send you back to the login page.
    await page.goto(`/w/${WS_A}`);
    await expect(page).toHaveURL(/\/login\?next=/);
  });

  test("rejects a wrong password with an inline message", async ({ page, health }) => {
    health.allow(/^HTTP 401 POST \/api\/auth\/login$/);
    await page.goto("/login");
    await page.getByLabel("Work email").fill(DEMO.email);
    await page.getByLabel("Password").fill("definitely-wrong");
    await page.getByRole("button", { name: "Sign in", exact: true }).click();
    await expect(page.getByText("That email and password don't match.", { exact: false })).toBeVisible();
    await expect(page).toHaveURL(/\/login/);
  });

  test("validates the form before calling the API", async ({ page }) => {
    await page.goto("/login");
    await page.getByRole("button", { name: "Sign in", exact: true }).click();
    await expect(page.getByText("Enter a valid email address.")).toBeVisible();
    await expect(page.getByText("Enter your password.")).toBeVisible();
  });

  test("returns to the requested page after signing in", async ({ page }) => {
    await page.goto(`/w/${WS_A}/world`);
    await expect(page).toHaveURL(/\/login\?next=/);
    await page.getByLabel("Work email").fill(DEMO.email);
    await page.getByLabel("Password").fill(DEMO.password);
    await page.getByRole("button", { name: "Sign in", exact: true }).click();
    await expect(page).toHaveURL(new RegExp(`/w/${WS_A}/world$`));
    await expect(page.getByRole("heading", { level: 1, name: "World state" })).toBeVisible();
  });
});
