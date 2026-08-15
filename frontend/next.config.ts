import type { NextConfig } from "next";

// The Django process serves the API and the generated cards. Proxying both through Next keeps
// the app on one origin, so there is no CORS configuration to keep in sync between the two.
const backend = process.env.BACKEND_ORIGIN ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  // Next 16 writes an AGENTS.md and a CLAUDE.md into this folder on boot. This repo's agent
  // instructions live at its root, and a second pair generated per `pnpm dev` is noise.
  agentRules: false,
  async rewrites() {
    return [
      { source: "/api/:path*", destination: `${backend}/api/:path*` },
      { source: "/media/:path*", destination: `${backend}/media/:path*` },
    ];
  },
};

export default nextConfig;
