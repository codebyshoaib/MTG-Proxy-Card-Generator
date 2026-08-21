import { NextRequest, NextResponse } from "next/server";

/**
 * Same gate as Django's DemoBasicAuthMiddleware. The browser authenticates to this origin;
 * rewrites forward Authorization to the API so /api and /media stay reachable.
 * Leave DEMO_BASIC_AUTH_* unset locally.
 */
export function middleware(request: NextRequest) {
  const user = process.env.DEMO_BASIC_AUTH_USER?.trim();
  const password = process.env.DEMO_BASIC_AUTH_PASSWORD?.trim();
  if (!user || !password) {
    return NextResponse.next();
  }

  const header = request.headers.get("authorization") ?? "";
  if (header.startsWith("Basic ")) {
    try {
      const decoded = atob(header.slice(6));
      const sep = decoded.indexOf(":");
      const gotUser = decoded.slice(0, sep);
      const gotPassword = decoded.slice(sep + 1);
      if (gotUser === user && gotPassword === password) {
        return NextResponse.next();
      }
    } catch {
      // fall through to 401
    }
  }

  return new NextResponse("Authentication required.", {
    status: 401,
    headers: { "WWW-Authenticate": 'Basic realm="MTG demo"' },
  });
}

export const config = {
  // Let Next serve its own assets and the runtime API/media proxies without double-gating
  // static files. /api and /media still hit this middleware first (same basic auth as pages).
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
