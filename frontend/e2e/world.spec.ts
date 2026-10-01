import { expect, RAZORPAY_ENTITY, test, WS_A } from "./fixtures";

test("world state lists entities and opens an entity page with facts and history", async ({ page }) => {
  await page.goto(`/w/${WS_A}/world`);
  await expect(page.getByRole("heading", { level: 1, name: "World state" })).toBeVisible();
  await expect(page.getByRole("region", { name: /^Subjects/ })).toBeVisible();
  await expect(page.getByRole("region", { name: /^Competitors/ })).toBeVisible();

  // Search narrows the grid
  await page.getByRole("textbox", { name: "Search entities" }).fill("cashfree");
  await expect(page.getByRole("link", { name: /^Cashfree Payments/ })).toBeVisible();
  await expect(page.getByRole("link", { name: /^Razorpay Subject/ })).toHaveCount(0);
  await page.getByRole("textbox", { name: "Search entities" }).fill("");

  await page.getByRole("link", { name: /^Razorpay Subject/ }).click();
  await expect(page).toHaveURL(new RegExp(`/world/${RAZORPAY_ENTITY}$`));
  await expect(page.getByRole("heading", { level: 1, name: "Razorpay" })).toBeVisible();

  const facts = page.getByRole("region", { name: "Tracked facts" });
  await expect(facts.getByRole("row", { name: /^Standard domestic fee/ })).toBeVisible();

  // Fact history drawer
  await facts.getByRole("button", { name: /^History of Standard domestic fee/ }).click();
  const drawer = page.getByRole("dialog");
  await expect(drawer).toBeVisible();
  await expect(drawer.getByText("0% for the first 90 days, then 2%").first()).toBeVisible();
  await expect(drawer.getByText("2% flat on domestic cards & UPI").first()).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(drawer).toBeHidden();

  await expect(page.getByRole("link", { name: "View intelligence" })).toHaveAttribute("href", /\/intel\?entity=/);
});
