import { proxyToBackend } from "@/lib/backend-proxy";

type Ctx = { params: Promise<{ path: string[] }> };

/** Generated card PNGs. Browser already authed to this origin; we forward that to Django. */
export async function GET(request: Request, ctx: Ctx) {
  return proxyToBackend(request, "media", (await ctx.params).path);
}
