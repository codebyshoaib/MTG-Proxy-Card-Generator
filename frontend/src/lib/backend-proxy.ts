/**
 * Runtime proxy to Django. next.config rewrites bake BACKEND_ORIGIN at build time; on Render
 * that often becomes the localhost default and /api/options dies. Reading the env here means
 * a correct value at runtime is enough — no rebuild required after fixing the env var.
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

export async function proxyToBackend(
  request: Request,
  prefix: "api" | "media",
  path: string[],
): Promise<Response> {
  const origin = (process.env.BACKEND_ORIGIN || "http://127.0.0.1:8000").replace(
    /\/$/,
    "",
  );
  if (!origin) {
    return Response.json(
      { detail: "BACKEND_ORIGIN is not set on the frontend service." },
      { status: 502 },
    );
  }

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
    return Response.json({ detail: `Backend proxy failed: ${message}` }, { status: 502 });
  }

  const out = new Headers();
  upstream.headers.forEach((value, key) => {
    if (!HOP_BY_HOP.has(key.toLowerCase())) {
      out.set(key, value);
    }
  });

  return new Response(upstream.body, { status: upstream.status, headers: out });
}
