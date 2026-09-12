import type { NextConfig } from "next";

if (process.env.NEXT_PUBLIC_ACCOUNTS_ENABLED === "true" && process.env.NEXT_PUBLIC_DEMO_API_KEY) {
  throw new Error("Account builds must not contain NEXT_PUBLIC_DEMO_API_KEY.");
}

const nextConfig: NextConfig = {
  output: "standalone",
  async headers() {
    const apiOrigin = new URL(process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000").origin;
    const scripts = process.env.NODE_ENV === "development" ? "'self' 'unsafe-inline' 'unsafe-eval'" : "'self' 'unsafe-inline'";
    return [{ source: "/:path*", headers: [
      { key: "X-Content-Type-Options", value: "nosniff" },
      { key: "X-Frame-Options", value: "DENY" },
      { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
      { key: "Content-Security-Policy", value: [
        "default-src 'self'", `script-src ${scripts}`, "style-src 'self' 'unsafe-inline'",
        `connect-src 'self' ${apiOrigin}`, "img-src 'self' data: blob:", "font-src 'self'",
        "frame-src 'self' blob:", "object-src 'none'", "base-uri 'self'", "form-action 'self'",
        "frame-ancestors 'none'",
      ].join("; ") },
    ] }];
  },
};

export default nextConfig;
