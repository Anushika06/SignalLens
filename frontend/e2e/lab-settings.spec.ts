import { expect, expectToast, test, WS_A } from "./fixtures";

test("demo lab: edit a sandbox page, preview it and save", async ({ page, health }) => {
  // The preview iframe is sandboxed without allow-scripts on purpose; Chromium logs that.
  health.allow(/^console\.error: Blocked script execution in 'about:srcdoc'/);
  await page.goto(`/lab?from=${WS_A}`);
  await expect(page.getByRole("heading", { level: 1, name: "Demo lab" })).toBeVisible();
  const pages = page.getByRole("navigation", { name: "Sandbox pages" });
  await pages.getByRole("button", { name: /Acme Pay — Pricing/ }).click();

  const editor = page.getByRole("region", { name: "Acme Pay — Pricing" });
  const save = editor.getByRole("button", { name: "Save page" });
  await expect(save).toBeDisabled();

  const html = editor.getByRole("textbox", { name: "HTML" });
  const original = await html.inputValue();
  const fee = `1.${Date.now() % 90 + 10}% per transaction`;
  const edited = original.replace(/<td class="fee">[^<]*<\/td>/, `<td class="fee">${fee}</td>`);
  expect(edited).not.toBe(original);
  await html.fill(edited);

  await expect(save).toBeEnabled();
  await expect(editor.frameLocator("iframe").getByText(fee)).toBeVisible();
  await save.click();
  await expectToast(page, "Page saved");
  await expect(save).toBeDisabled();
});

test.describe("settings", () => {
  test("edits and saves the company profile", async ({ page }) => {
    await page.goto(`/w/${WS_A}/settings`);
    await expect(page.getByRole("heading", { level: 1, name: "Settings" })).toBeVisible();
    const profile = page.getByRole("region", { name: "Company profile" });
    const save = profile.getByRole("button", { name: "Save profile" });
    await expect(save).toBeDisabled();

    const relationship = profile.getByRole("textbox", { name: "Your relationship to what you monitor" });
    await relationship.fill(`Razorpay is our most direct competitor in SMB onboarding. (updated ${Date.now()})`);
    await expect(save).toBeEnabled();
    await save.click();
    await expectToast(page, "Company profile saved");
    await expect(profile.getByText("All changes saved.")).toBeVisible();
  });

  test("lists teams and adds a new one", async ({ page }) => {
    await page.goto(`/w/${WS_A}/settings`);
    const teams = page.getByRole("region", { name: "Teams" });
    await expect(teams.getByRole("heading", { name: "Strategy", level: 3 })).toBeVisible();
    await expect(teams.getByText("priya.raman@kivo.in").first()).toBeVisible();

    const name = `Partnerships ${Date.now().toString(36)}`;
    await teams.getByRole("button", { name: "Add team" }).click();
    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible();
    await dialog.getByLabel(/^Team name/).fill(name);
    await dialog.locator("button[type=submit]").click();

    await expectToast(page, `Created “${name}”`);
    await expect(teams.getByRole("heading", { name, level: 3 })).toBeVisible();
  });
});
