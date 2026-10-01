/**
 * Where to go after signing in. Only same-origin relative paths are accepted, so a crafted
 * `/login?next=https://evil.example` (or `//evil.example`) can't turn login into an open redirect.
 */
export function safeNextPath(raw: string | null | undefined): string {
  if (!raw) return "/";
  const value = raw.trim();
  if (!value.startsWith("/") || value.startsWith("//") || value.includes("\\")) return "/";
  if (Array.from(value).some((char) => char.charCodeAt(0) < 32)) return "/";
  // Never bounce back to the login page itself.
  if (/^\/login(?:[/?#]|$)/.test(value)) return "/";
  return value;
}
