import type { NextRequest } from "next/server";

/**
 * 推导「对外可访问」的站点 origin（2026-09-26 安全审计复扫修复）。
 *
 * 背景：反代部署下 `req.nextUrl.origin` 并不等于浏览器地址栏的 origin——实测
 * Nginx 已正确转发 `Host` / `X-Forwarded-Host` / `X-Forwarded-Proto`，但 Next
 * 仍把它解析成监听地址（`http://0.0.0.0:3000`）或归一化成 `localhost`。直接拿它
 * 拼绝对地址会导致 OAuth 回调把用户导到不可达地址，或把 redirect_uri 注册错。
 *
 * 规则与 `rate-limit.ts` 的 `resolveClientIp` 保持一致：只有显式声明
 * `JIARU_TRUST_PROXY=1`（反向代理会覆盖这些头）时才采信转发头，否则回退
 * `req.nextUrl.origin`，避免开放重定向。
 */
export function publicOrigin(
  req: NextRequest,
  env: Record<string, string | undefined> = process.env
): string {
  if (env.JIARU_TRUST_PROXY === "1") {
    const host =
      req.headers.get("x-forwarded-host")?.trim() || req.headers.get("host")?.trim();
    if (host) {
      const protoHeader = req.headers.get("x-forwarded-proto");
      const proto = protoHeader?.split(",")[0].trim() || "https";
      return `${proto}://${host}`;
    }
  }
  return req.nextUrl.origin;
}
