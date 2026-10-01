#!/usr/bin/env node
/**
 * Starts the mock API (scripts/mock-api.mjs, port 8010) and `next dev` pointed at it, in one
 * command that works the same on Windows, macOS and Linux. Ctrl+C stops both.
 *
 *   npm run dev:mock
 *
 * Environment: MOCK_PORT (default 8010), PORT for Next.js (default 3000), plus any mock flags
 * such as MOCK_NO_KEYS=1.
 */
import { spawn } from "node:child_process";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const require = createRequire(import.meta.url);
const mockPort = process.env.MOCK_PORT ?? "8010";

const children = [];

function start(name, args, env) {
  const child = spawn(process.execPath, args, { stdio: "inherit", env: { ...process.env, ...env } });
  child.on("exit", (code, signal) => {
    console.log(`[dev:mock] ${name} exited (${signal ?? code}); stopping.`);
    shutdown(code ?? 0);
  });
  children.push(child);
  return child;
}

let stopping = false;
function shutdown(code) {
  if (stopping) return;
  stopping = true;
  for (const child of children) {
    if (child.exitCode === null) child.kill();
  }
  process.exit(code);
}

process.on("SIGINT", () => shutdown(0));
process.on("SIGTERM", () => shutdown(0));

start("mock API", [join(here, "mock-api.mjs")], { MOCK_PORT: mockPort });
start("next dev", [require.resolve("next/dist/bin/next"), "dev"], {
  SIGNALLENS_API_URL: `http://127.0.0.1:${mockPort}`,
});
