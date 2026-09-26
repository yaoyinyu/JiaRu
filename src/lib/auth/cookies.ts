import { NextRequest, NextResponse } from "next/server";
import { resolveClientIp } from "../rate-limit.ts";

/**
 * 认证 Cookie 工具：access token（2h）与 refresh token（30 天）。
 * 均为 httpOnly + SameSite=Lax，生产环境加 Secure。
 */

export const ACCESS_COOKIE = "jiaru_access";
export const REFRESH_COOKIE = "jiaru_refresh";

const isSecure = () => process.env.NODE_ENV === "production";

export function getTokensFromRequest(req: NextRequest): { access: string | null; refresh: string | null } {
  return {
    access: req.cookies.get(ACCESS_COOKIE)?.value ?? null,
    refresh: req.cookies.get(REFRESH_COOKIE)?.value ?? null,
  };
}

export function setAuthCookies(res: NextResponse, accessToken: string, refreshToken: string): void {
  res.cookies.set(ACCESS_COOKIE, accessToken, {
    httpOnly: true,
    sameSite: "lax",
    secure: isSecure(),
    path: "/",
    maxAge: 2 * 60 * 60,
  });
  res.cookies.set(REFRESH_COOKIE, refreshToken, {
    httpOnly: true,
    sameSite: "lax",
    secure: isSecure(),
    path: "/",
    maxAge: 30 * 24 * 60 * 60,
  });
}

export function clearAuthCookies(res: NextResponse): void {
  res.cookies.set(ACCESS_COOKIE, "", { httpOnly: true, sameSite: "lax", secure: isSecure(), path: "/", maxAge: 0 });
  res.cookies.set(REFRESH_COOKIE, "", { httpOnly: true, sameSite: "lax", secure: isSecure(), path: "/", maxAge: 0 });
}

/**
 * 从请求中提取客户端 IP（2026-09-24 安全审计修复 L1）。
 *
 * 旧实现无条件采信 `x-forwarded-for` 首段——客户端可伪造，会污染 `audit_logs.ip`
 * 与短信开发态判定。现改为：只在显式声明 `JIARU_TRUST_PROXY=1`（Nginx 会覆盖
 * XFF 并注入 `X-Real-IP: $remote_addr`）时才采信代理头；否则一律返回 null
 * （调用方按“未知”处理），绝不把伪造值写进审计记录。
 */
export function getClientIp(req: NextRequest): string | null {
  if (process.env.JIARU_TRUST_PROXY === "1") {
    const ip = resolveClientIp(req.headers);
    return ip === "unknown" ? null : ip;
  }
  return null;
}
