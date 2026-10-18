import { NextRequest, NextResponse } from "next/server";

// A strict Content-Security-Policy with a new nonce for every request: only our own scripts and styles run, nothing is loaded from another site,
// and the page cannot be framed. (Development needs 'unsafe-eval' for React's debugging tools; production does not.)
const STYLE_ATTR_HASHES: string[] = [];

export function proxy(request: NextRequest) {
  const nonce = Buffer.from(crypto.randomUUID()).toString("base64");
  const dev = process.env.NODE_ENV === "development";
  const csp = [
    "default-src 'self'",
    `script-src 'self' 'nonce-${nonce}' 'strict-dynamic'${dev ? " 'unsafe-eval'" : ""}`,
    `style-src 'self' 'nonce-${nonce}'`,
    // Style ATTRIBUTES set by Next itself (its screen-reader route announcer; in development also its dev tools). Production allows only the exact values by hash.
    dev ? "style-src-attr 'unsafe-inline'" : `style-src-attr 'unsafe-hashes' ${STYLE_ATTR_HASHES.map((h) => `'${h}'`).join(" ")}`,
    "img-src 'self' data:",
    "font-src 'self'",
    "connect-src 'self'",
    "object-src 'none'",
    "base-uri 'none'",
    "form-action 'self'",
    "frame-ancestors 'none'",
    ...(dev ? [] : ["upgrade-insecure-requests"]),
  ].join("; ");

  const headers = new Headers(request.headers);
  headers.set("x-nonce", nonce);
  headers.set("Content-Security-Policy", csp);
  const response = NextResponse.next({ request: { headers } });
  response.headers.set("Content-Security-Policy", csp);
  return response;
}

export const config = {
  matcher: [{ source: "/((?!_next/static|_next/image|favicon.ico).*)", missing: [{ type: "header", key: "next-router-prefetch" }, { type: "header", key: "purpose", value: "prefetch" }] }],
};
