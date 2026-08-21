import type { NextConfig } from "next";

// /api and /media are handled at runtime by app/api/[...path] and app/media/[...path] so
// BACKEND_ORIGIN is read per request. Build-time rewrites used to bake in localhost on Render.

const nextConfig: NextConfig = {
  // Next 16 writes an AGENTS.md and a CLAUDE.md into this folder on boot. This repo's agent
  // instructions live at its root, and a second pair generated per `pnpm dev` is noise.
  agentRules: false,
};

export default nextConfig;
