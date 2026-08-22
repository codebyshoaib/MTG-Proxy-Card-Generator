import { proxyToBackend } from "@/lib/backend-proxy";

type Ctx = { params: Promise<{ path: string[] }> };

/** Generated card PNGs — proxied to Django media storage. */
export async function GET(request: Request, ctx: Ctx) {
  return proxyToBackend(request, "media", (await ctx.params).path);
}
