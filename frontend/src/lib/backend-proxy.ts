/**
 * Runtime proxy to Django.
 *
 * next.config rewrites bake BACKEND_ORIGIN at build time (often localhost on Render).
 * Browser Basic Auth is also unreliable on fetch() — some sessions load the page but omit
 * Authorization on XHR. Middleware already gated the user; we attach DEMO_BASIC_AUTH_* to
 * the upstream call so Django accepts it.
 */

const HOP_BY_HOP = new Set([
  "connection",
  "keep-alive",
  "proxy-authenticate",
  "proxy-authorization",
  "te",
  "trailers",
  "transfer-encoding",
  "upgrade",
  "host",
  "content-length",
]);

function backendOrigin(): string {
  return (process.env.BACKEND_ORIGIN || "http://127.0.0.1:8000").replace(/\/$/, "");
}

function upstreamAuth(): string | null {
  const user = process.env.DEMO_BASIC_AUTH_USER?.trim();
  const password = process.env.DEMO_BASIC_AUTH_PASSWORD?.trim();
  if (!user || !password) return null;
  return `Basic ${Buffer.from(`${user}:${password}`).toString("base64")}`;
}

export async function proxyToBackend(
  request: Request,
  prefix: "api" | "media",
  path: string[],
): Promise<Response> {
  const origin = backendOrigin();
  const incoming = new URL(request.url);
  const target = `${origin}/${prefix}/${path.map(encodeURIComponent).join("/")}${incoming.search}`;

  const headers = new Headers();
  request.headers.forEach((value, key) => {
    if (!HOP_BY_HOP.has(key.toLowerCase())) {
      headers.set(key, value);
    }
  });

  // Prefer server-side credentials for Django. Client Authorization is for Next middleware.
  const auth = upstreamAuth();
  if (auth) {
    headers.set("authorization", auth);
  }

  const init: RequestInit = {
    method: request.method,
    headers,
    redirect: "manual",
  };
  if (request.method !== "GET" && request.method !== "HEAD") {
    init.body = await request.arrayBuffer();
  }

  let upstream: Response;
  try {
    upstream = await fetch(target, init);
  } catch (error) {
    const message = error instanceof Error ? error.message : "upstream unreachable";
    return Response.json(
      {
        detail: `Backend proxy failed talking to ${origin}: ${message}`,
      },
      { status: 502 },
    );
  }

  const out = new Headers();
  upstream.headers.forEach((value, key) => {
    if (!HOP_BY_HOP.has(key.toLowerCase())) {
      out.set(key, value);
    }
  });

  return new Response(upstream.body, { status: upstream.status, headers: out });
}
