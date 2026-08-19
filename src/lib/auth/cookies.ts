import { NextRequest, NextResponse } from "next/server";

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

/** 从请求中提取客户端 IP（含代理头回退） */
export function getClientIp(req: NextRequest): string | null {
  const forwarded = req.headers.get("x-forwarded-for");
  if (forwarded) return forwarded.split(",")[0].trim();
  return req.headers.get("x-real-ip") ?? null;
}
