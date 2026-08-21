import { proxyToBackend } from "@/lib/backend-proxy";

type Ctx = { params: Promise<{ path: string[] }> };

export async function GET(_request: Request, ctx: Ctx) {
  return proxyToBackend(_request, "api", (await ctx.params).path);
}

export async function POST(request: Request, ctx: Ctx) {
  return proxyToBackend(request, "api", (await ctx.params).path);
}

export async function PUT(request: Request, ctx: Ctx) {
  return proxyToBackend(request, "api", (await ctx.params).path);
}

export async function PATCH(request: Request, ctx: Ctx) {
  return proxyToBackend(request, "api", (await ctx.params).path);
}

export async function DELETE(request: Request, ctx: Ctx) {
  return proxyToBackend(request, "api", (await ctx.params).path);
}
