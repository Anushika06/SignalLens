import { defineConfig, devices } from "@playwright/test";

/**
 * End-to-end tests against the mock API (scripts/mock-api.mjs) and a production build of the
 * app. `scripts/e2e-server.mjs` builds the app if needed (rewrites are fixed at build time, so
 * the build must target the mock), then serves it with `next start`.
 *
 * Dedicated ports (app 3100, mock 8020) keep the tests away from `npm run dev` / `dev:mock`.
 * The server is never reused, so every run starts from the mock's pristine in-memory fixtures.
 */
const port = Number(process.env.E2E_PORT ?? 3100);
const baseURL = `http://127.0.0.1:${port}`;
const isCI = !!process.env.CI;

export default defineConfig({
  testDir: "./e2e",
  outputDir: "./test-results",
  fullyParallel: true,
  forbidOnly: isCI,
  retries: isCI ? 1 : 0,
  workers: isCI ? 2 : 3,
  timeout: 45_000,
  expect: { timeout: 10_000 },
  reporter: isCI ? [["list"], ["html", { open: "never" }], ["github"]] : [["list"], ["html", { open: "never" }]],
  use: {
    baseURL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
    locale: "en-GB",
    timezoneId: "Asia/Kolkata",
  },
  projects: [
    { name: "setup", testMatch: /auth\.setup\.ts/ },
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"], storageState: "e2e/.auth/demo.json" },
      dependencies: ["setup"],
    },
  ],
  webServer: {
    command: "node scripts/e2e-server.mjs",
    url: `${baseURL}/login`,
    reuseExistingServer: false,
    // First run includes a production build.
    timeout: 300_000,
    stdout: "pipe",
    stderr: "pipe",
    env: { E2E_PORT: String(port) },
  },
});
