import type { NextConfig } from "next";

/**
 * The browser only ever talks to this app's own origin. Every `/api/*` request is proxied to
 * the SignalLens backend, so the backend's httpOnly `sl_session` cookie is first-party and no
 * CORS configuration is needed.
 *
 * Note: rewrites are resolved when the server starts (`next dev`) or at build time
 * (`next build`), so set SIGNALLENS_API_URL before running either.
 */
const apiUrl = (process.env.SIGNALLENS_API_URL ?? "http://127.0.0.1:8000").replace(/\/+$/, "");

const nextConfig: NextConfig = {
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${apiUrl}/api/:path*` }];
  },
};

export default nextConfig;
