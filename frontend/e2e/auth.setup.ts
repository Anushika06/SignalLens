import { AUTH_FILE, SIGNED_OUT_ME, signIn, test as setup } from "./fixtures";

/** Signs in once as the demo user; the other tests reuse the session cookie. */
setup("sign in as the demo user", async ({ page, health }) => {
  health.allow(SIGNED_OUT_ME);
  await signIn(page);
  await page.context().storageState({ path: AUTH_FILE });
});
