import { NextRequest, NextResponse } from "next/server";

/**
 * Gate the Milestone 1 demo. Browser Basic Auth is unreliable on fetch() — the document
 * request gets Authorization, then XHR often does not, so /api/options 401s after login.
 * After a successful Basic challenge we set an httpOnly cookie; later requests may present
 * either the Basic header or that cookie.
 *
 * Leave DEMO_BASIC_AUTH_* unset locally so tests and `pnpm dev` stay open.
 */

const COOKIE = "mtg_demo";

function configured() {
  const user = process.env.DEMO_BASIC_AUTH_USER?.trim();
  const password = process.env.DEMO_BASIC_AUTH_PASSWORD?.trim();
  return user && password ? { user, password } : null;
}

function basicOk(header: string, user: string, password: string): boolean {
  if (!header.startsWith("Basic ")) return false;
  try {
    const decoded = atob(header.slice(6));
    const sep = decoded.indexOf(":");
    return decoded.slice(0, sep) === user && decoded.slice(sep + 1) === password;
  } catch {
    return false;
  }
}

export function middleware(request: NextRequest) {
  const creds = configured();
  if (!creds) {
    return NextResponse.next();
  }

  const authed =
    basicOk(request.headers.get("authorization") ?? "", creds.user, creds.password) ||
    request.cookies.get(COOKIE)?.value === "1";

  if (!authed) {
    return new NextResponse("Authentication required.", {
      status: 401,
      headers: { "WWW-Authenticate": 'Basic realm="MTG demo"' },
    });
  }

  const response = NextResponse.next();
  // Refresh the cookie on every successful hit so a long generate poll does not drop it.
  response.cookies.set(COOKIE, "1", {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    maxAge: 60 * 60 * 12,
  });
  return response;
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
