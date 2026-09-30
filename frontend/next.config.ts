import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // P10-1D: standalone server for the production container runner.
  // Build output (routes, prerendering, static evidence) is unchanged;
  // only the packaging of the server runtime differs.
  output: "standalone",
  turbopack: {
    root: import.meta.dirname,
  },
};

export default nextConfig;
