import { fileURLToPath } from "node:url";

import { defineConfig } from "vitest/config";

/**
 * Unit and component tests (Vitest + Testing Library on jsdom). End-to-end tests live in
 * `e2e/` and run with Playwright (`npm run test:e2e`), so they are excluded here.
 */
export default defineConfig({
  resolve: {
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
  oxc: {
    jsx: { runtime: "automatic" },
  },
  test: {
    environment: "jsdom",
    include: ["src/**/*.test.{ts,tsx}"],
    setupFiles: ["./src/test/setup.ts"],
    css: false,
    restoreMocks: true,
  },
});
