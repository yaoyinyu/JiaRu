const nextConfig = {
  // 不暴露 X-Powered-By: Next.js，减少框架指纹（2026-09-24 安全加固）
  poweredByHeader: false,
  allowedDevOrigins: [
    '192.168.1.100',
    '127.0.0.1',
    'localhost',
    '*.trycloudflare.com',
    '*.cpolar.cn',
    '*.cpolar.top',
    '*.cpolar.io',
    '*.ngrok-free.app',
  ],
  async headers() {
    // 安全响应头（HSTS 与 CSP 放在 Nginx TLS 终结层，见 deploy/nginx/jiaru.conf）。
    // 这里只放不会破坏 WASM/worker/blob 运行时也不依赖 HTTPS 的通用头。
    const baseSecurityHeaders = [
      { key: "X-Content-Type-Options", value: "nosniff" },
      { key: "X-Frame-Options", value: "SAMEORIGIN" },
      { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
      { key: "X-DNS-Prefetch-Control", value: "off" },
      { key: "Cross-Origin-Opener-Policy", value: "same-origin" },
    ];
    return [
      {
        source: "/(.*)",
        headers: baseSecurityHeaders,
      },
      {
        source: "/ar-demo",
        headers: [
          ...baseSecurityHeaders,
          {
            key: "Permissions-Policy",
            value: 'camera=(self "http://localhost:8080" "http://127.0.0.1:8080"), microphone=()',
          },
        ],
      },
      {
        source: "/ar-tryon",
        headers: [
          ...baseSecurityHeaders,
          {
            key: "Permissions-Policy",
            value: "camera=(self), microphone=()",
          },
        ],
      },
    ];
  },
};
export default nextConfig;
