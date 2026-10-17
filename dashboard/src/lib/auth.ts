/**
 * Password gate for the read-only dashboard.
 * Uses Web Crypto so the same helpers work in Edge middleware and Node route handlers.
 */

export const AUTH_COOKIE = "ght_dash_session";

const SESSION_TTL_SECONDS = 60 * 60 * 12; // 12 hours

function secretMaterial(): string {
  const password = process.env.DASHBOARD_PASSWORD ?? "";
  const pepper = process.env.DASHBOARD_SESSION_SECRET ?? password;
  if (!pepper) {
    return "dev-insecure-dashboard-secret";
  }
  return pepper;
}

export function isAuthConfigured(): boolean {
  return Boolean(process.env.DASHBOARD_PASSWORD?.trim());
}

function timingSafeEqualString(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  let mismatch = 0;
  for (let i = 0; i < a.length; i += 1) {
    mismatch |= a.charCodeAt(i) ^ b.charCodeAt(i);
  }
  return mismatch === 0;
}

export function verifyPassword(candidate: string): boolean {
  const expected = process.env.DASHBOARD_PASSWORD ?? "";
  if (!expected) {
    // No password configured: allow local/dev access (documented).
    return true;
  }
  return timingSafeEqualString(candidate, expected);
}

async function hmacHex(message: string): Promise<string> {
  const keyData = new TextEncoder().encode(secretMaterial());
  const key = await crypto.subtle.importKey(
    "raw",
    keyData,
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const sig = await crypto.subtle.sign(
    "HMAC",
    key,
    new TextEncoder().encode(message),
  );
  return Array.from(new Uint8Array(sig))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

export async function createSessionToken(): Promise<string> {
  const exp = Math.floor(Date.now() / 1000) + SESSION_TTL_SECONDS;
  const payload = `ok.${exp}`;
  const sig = await hmacHex(payload);
  return `${payload}.${sig}`;
}

export async function isValidSessionToken(
  token: string | undefined | null,
): Promise<boolean> {
  if (!token) return false;
  const parts = token.split(".");
  if (parts.length !== 3) return false;
  const [ok, expStr, sig] = parts;
  if (ok !== "ok") return false;
  const exp = Number(expStr);
  if (!Number.isFinite(exp) || exp < Math.floor(Date.now() / 1000)) return false;
  const payload = `${ok}.${expStr}`;
  const expected = await hmacHex(payload);
  return timingSafeEqualString(sig, expected);
}

export function cookieOptions(maxAge = SESSION_TTL_SECONDS) {
  return {
    httpOnly: true,
    sameSite: "lax" as const,
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge,
  };
}
