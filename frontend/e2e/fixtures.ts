import { test as base, expect, type Page } from "@playwright/test";

/** Seeded demo account (accepted by the mock API and by `signallens seed-demo`). */
export const DEMO = { email: "demo@signallens.app", password: "signallens-demo" } as const;

/** Fixture ids from scripts/mock-api.mjs (see frontend/README.md → "the mock API"). */
export const WS_A = "00000000-0000-4000-8000-001000000001"; // "Razorpay watch", monitoring
export const WS_B = "00000000-0000-4000-8000-001000000002"; // Stripe plan awaiting approval
export const PLAN_B = "00000000-0000-4000-8000-002000000002";
export const HEADLINE_REPORT = "00000000-0000-4000-8000-004000000001"; // 0% platform fee card
export const RAZORPAY_ENTITY = "00000000-0000-4000-8000-005000000001";

export const AUTH_FILE = "e2e/.auth/demo.json";

type HealthMonitor = {
  /** Accept a problem matching this pattern (e.g. the 401 from /api/auth/me while signed out). */
  allow: (pattern: RegExp) => void;
  /** Problems recorded so far (for debugging). */
  problems: () => string[];
};

const ABORTED = /ERR_ABORTED|NS_BINDING_ABORTED|cancelled/i;

/**
 * Failures of the test machine's own network stack (e.g. Windows running out of socket buffers
 * under heavy load), not of the app. They are recorded as an annotation instead of failing.
 */
const ENVIRONMENT = /ERR_NO_BUFFER_SPACE|ERR_INSUFFICIENT_RESOURCES|ERR_NETWORK_CHANGED/i;

/**
 * Endpoints the app calls that the mock API does not implement yet. Keep this list empty
 * whenever possible: an entry hides a real regression of the same shape.
 */
const MOCK_GAPS: RegExp[] = [];

function sameOriginPath(origin: string, url: string): string | null {
  try {
    const parsed = new URL(url);
    return parsed.origin === origin ? parsed.pathname : null;
  } catch {
    return null;
  }
}

/**
 * Every test gets an automatic health check: it fails if the page logged a console error, threw
 * an uncaught exception, got an HTTP error from the app's own origin (API or assets), or had a
 * same-origin request fail at the network level. Aborted requests are ignored — they are
 * cancelled prefetches and in-flight requests from pages the test navigated away from.
 *
 * The browser logs "Failed to load resource" for every HTTP error; those are judged by the
 * response rule instead (which knows the URL), so a test can allow one specific expected 4xx.
 */
export const test = base.extend<{ health: HealthMonitor }>({
  health: [
    async ({ page, baseURL }, use, testInfo) => {
      const origin = new URL(baseURL ?? "http://127.0.0.1:3100").origin;
      const problems: string[] = [];
      const allowed: RegExp[] = [...MOCK_GAPS];

      page.on("console", (message) => {
        if (message.type() !== "error") return;
        const text = message.text();
        if (text.startsWith("Failed to load resource")) return;
        problems.push(`console.error: ${text} (on ${page.url()})`);
      });
      page.on("pageerror", (error) => problems.push(`uncaught exception: ${error.message} (on ${page.url()})`));
      page.on("response", (response) => {
        if (response.status() < 400) return;
        const path = sameOriginPath(origin, response.url());
        if (path === null) return;
        problems.push(`HTTP ${response.status()} ${response.request().method()} ${path}`);
      });
      page.on("requestfailed", (request) => {
        const reason = request.failure()?.errorText ?? "failed";
        if (ABORTED.test(reason)) return;
        const path = sameOriginPath(origin, request.url());
        if (path === null) return;
        if (ENVIRONMENT.test(reason)) {
          testInfo.annotations.push({ type: "environment-network", description: `${request.method()} ${path} (${reason})` });
          return;
        }
        problems.push(`request failed: ${request.method()} ${path} (${reason})`);
      });

      await use({ allow: (pattern) => allowed.push(pattern), problems: () => [...problems] });

      const unexpected = problems.filter((problem) => !allowed.some((pattern) => pattern.test(problem)));
      expect(unexpected, "console errors, uncaught exceptions or failed requests during the test").toEqual([]);
    },
    { auto: true },
  ],
});

export { expect };

/** The 401 that /api/auth/me returns while signed out (the login page asks who you are). */
export const SIGNED_OUT_ME = /^HTTP 401 GET \/api\/auth\/me$/;

/** Signs in through the login form and waits for the workspace list. */
export async function signIn(page: Page, account: { email: string; password: string } = DEMO) {
  await page.goto("/login");
  await page.getByLabel("Work email").fill(account.email);
  await page.getByLabel("Password").fill(account.password);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByRole("heading", { level: 1, name: "Workspaces" })).toBeVisible();
}

/** Any API call answered 401 because there is no session (expected while signed out). */
export const SIGNED_OUT_API = /^HTTP 401 GET \/api\//;

/**
 * Waits until no toast is on screen. Toasts sit in the bottom-right corner, over sticky action
 * bars, and pause while the pointer is over them, so tests clear them before clicking there.
 */
export async function waitForToastsToClear(page: Page) {
  await expect(page.locator("[data-sonner-toast]")).toHaveCount(0, { timeout: 20_000 });
}

/** Waits for a toast with this text. */
export async function expectToast(page: Page, text: string | RegExp) {
  await expect(page.getByRole("region", { name: /Notifications/ }).getByText(text).first()).toBeVisible();
}
