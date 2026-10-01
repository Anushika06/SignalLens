#!/usr/bin/env node
/**
 * Server for the Playwright end-to-end tests: the mock API (scripts/mock-api.mjs) plus a
 * **production** build of the app (`next start`) whose `/api/*` rewrite points at the mock.
 * Playwright's `webServer` runs this; you rarely need to run it by hand.
 *
 * Why a production build and not `next dev`: no on-demand compilation (stable timings), no
 * dev-only overlays or warnings in the console, and Next 16 allows only one `next dev` per
 * project, so the tests never fight a dev server you already have running.
 *
 * The build goes to its own directory, `.next-e2e` (via NEXT_DIST_DIR, see next.config.ts), so
 * it never replaces — or is replaced by — a regular `npm run build` in `.next`. Rewrites are fixed
 * at build time, so the app is (re)built here when that build is missing, was built for a
 * different API URL, or is older than the sources.
 *
 * Environment: E2E_PORT (app, default 3100), E2E_MOCK_PORT (mock, default 8020),
 * MOCK_LATENCY_MS (default 0 here), E2E_SKIP_BUILD=1 (always reuse the existing e2e build),
 * E2E_FORCE_BUILD=1 (always rebuild).
 */
import { spawn, spawnSync } from "node:child_process";
import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const root = join(here, "..");
const require = createRequire(import.meta.url);
const nextBin = require.resolve("next/dist/bin/next");

const appPort = process.env.E2E_PORT ?? "3100";
const mockPort = process.env.E2E_MOCK_PORT ?? "8020";
const apiUrl = `http://127.0.0.1:${mockPort}`;
const distDir = ".next-e2e";
const nextEnv = { NEXT_DIST_DIR: distDir, SIGNALLENS_API_URL: apiUrl, NEXT_TELEMETRY_DISABLED: "1" };

function log(message) {
  console.log(`[e2e-server] ${message}`);
}

/** Newest modification time of the inputs that affect the build. */
function newestSourceMtime() {
  let newest = 0;
  const visit = (path) => {
    if (!existsSync(path)) return;
    const stat = statSync(path);
    if (stat.isDirectory()) {
      for (const entry of readdirSync(path)) visit(join(path, entry));
    } else if (!/\.test\.tsx?$/.test(path)) {
      newest = Math.max(newest, stat.mtimeMs);
    }
  };
  for (const entry of ["src", "public", "next.config.ts", "package.json", "postcss.config.mjs"]) {
    visit(join(root, entry));
  }
  return newest;
}

function buildReason() {
  if (process.env.E2E_FORCE_BUILD === "1") return "E2E_FORCE_BUILD=1";
  const buildId = join(root, distDir, "BUILD_ID");
  const manifest = join(root, distDir, "routes-manifest.json");
  if (!existsSync(buildId) || !existsSync(manifest)) return `no production build in ${distDir}`;
  const rewrites = readFileSync(manifest, "utf8");
  if (!rewrites.includes(`${apiUrl}/api/`)) return `the build's /api rewrite does not point at ${apiUrl}`;
  if (newestSourceMtime() > statSync(buildId).mtimeMs) return "sources changed since the last build";
  return null;
}

if (process.env.E2E_SKIP_BUILD === "1") {
  log("E2E_SKIP_BUILD=1: reusing the existing build.");
} else {
  const reason = buildReason();
  if (reason) {
    log(`building the app into ${distDir} (${reason}) with SIGNALLENS_API_URL=${apiUrl} …`);
    const result = spawnSync(process.execPath, [nextBin, "build"], {
      cwd: root,
      stdio: "inherit",
      env: { ...process.env, ...nextEnv },
    });
    if (result.status !== 0) {
      log("next build failed.");
      process.exit(result.status ?? 1);
    }
  } else {
    log(`reusing the existing build (already targets ${apiUrl}).`);
  }
}

const children = [];
let stopping = false;

function shutdown(code) {
  if (stopping) return;
  stopping = true;
  for (const child of children) {
    if (child.exitCode === null) child.kill();
  }
  process.exit(code);
}

function start(name, args, env) {
  const child = spawn(process.execPath, args, { cwd: root, stdio: "inherit", env: { ...process.env, ...env } });
  child.on("exit", (code, signal) => {
    if (!stopping) log(`${name} exited (${signal ?? code}); stopping.`);
    shutdown(code ?? 0);
  });
  children.push(child);
}

process.on("SIGINT", () => shutdown(0));
process.on("SIGTERM", () => shutdown(0));

start("mock API", [join(here, "mock-api.mjs")], {
  MOCK_PORT: mockPort,
  MOCK_LATENCY_MS: process.env.MOCK_LATENCY_MS ?? "0",
});
start("next start", [nextBin, "start", "-p", appPort, "-H", "127.0.0.1"], nextEnv);
