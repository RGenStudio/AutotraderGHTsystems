import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // postgres.js talks to Postgres from the Node server. Do not bundle it for the edge.
  serverExternalPackages: ["postgres", "@supabase/supabase-js"],
};

export default nextConfig;
