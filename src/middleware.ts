import { NextRequest, NextResponse } from "next/server";

/**
 * CSRF 防护（2026-09-24 安全审计修复）。
 *
 * 背景：所有写操作接口（verify-code / logout / bind-phone / PATCH /api/me /
 * DELETE identities）都依赖 Cookie 鉴权，此前仅靠 `SameSite=Lax` 兜底，
 * 服务端没有任何来源校验。这里对状态变更类请求强制校验 Origin：
 *  - Origin 缺失 → 拒绝（浏览器发起的跨站/本站写请求必然带 Origin）；
 *  - Origin 主机不在白名单 → 拒绝。
 *
 * 白名单 = 当前请求的 Host（生产域名自动包含）+ 环境变量
 * `JIARU_ALLOWED_ORIGINS`（逗号分隔，用于局域网 / 隧道联调，例如
 * `http://192.168.1.100:3000,https://xxx.trycloudflare.com`）。
 */

function allowedOrigins(req: NextRequest): Set<string> {
  const list = new Set<string>();
  list.add(req.nextUrl.origin);

  // `req.nextUrl.origin` 由请求 URL 推导，在部分部署形态下会归一化为 localhost，
  // 与浏览器实际携带的 Origin 不一致；因此同时用 Host 头 + 转发协议推导一份。
  const host = req.headers.get("host");
  if (host) {
    const protoHeader = req.headers.get("x-forwarded-proto");
    const proto = protoHeader?.split(",")[0].trim() || req.nextUrl.protocol.replace(":", "");
    list.add(`${proto}://${host}`);
    const port = host.split(":")[1];
    if (port) {
      // 本地联调兜底（仅非生产环境）：同一端口的 localhost / 127.0.0.1 互认
      if (process.env.NODE_ENV !== "production") {
        list.add(`${proto}://localhost:${port}`);
        list.add(`${proto}://127.0.0.1:${port}`);
      }
    }
  }

  const extra = process.env.JIARU_ALLOWED_ORIGINS;
  if (extra) {
    for (const item of extra.split(",")) {
      const value = item.trim();
      if (value) list.add(value);
    }
  }
  return list;
}

export function middleware(req: NextRequest) {
  const method = req.method.toUpperCase();
  // 只拦截状态变更类请求；GET/HEAD/OPTIONS 不产生副作用
  if (method === "GET" || method === "HEAD" || method === "OPTIONS") {
    return NextResponse.next();
  }

  // 微信 OAuth 回调由微信侧重定向而来，且自身带 state 校验，不受 CSRF 影响；
  // 但它是 GET，已在上面放行。这里额外排除回调路径以防未来改为 POST。
  if (req.nextUrl.pathname.startsWith("/api/auth/oauth/wechat/callback")) {
    return NextResponse.next();
  }

  const origin = req.headers.get("origin");
  if (!origin) {
    return NextResponse.json({ error: "缺少 Origin 请求头" }, { status: 403 });
  }
  if (!allowedOrigins(req).has(origin)) {
    return NextResponse.json({ error: "请求来源不被允许" }, { status: 403 });
  }
  return NextResponse.next();
}

export const config = {
  matcher: "/api/:path*",
};
