/**
 * Runtime proxy to Django.
 *
 * next.config rewrites bake BACKEND_ORIGIN at build time (often localhost on Render).
 * Routes under app/api/[...path] and app/media/[...path] forward at request time instead.
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
