import { NextRequest, NextResponse } from "next/server";
import { getAuthService } from "./server.ts";
import { getTokensFromRequest, setAuthCookies } from "./cookies.ts";
import { AuthError, type AuthTokens, type UserRow } from "./types.ts";

/**
 * 认证相关 Route Handler 共享工具。
 */

export interface AuthSession {
  user: UserRow;
  /** 非空表示 access 已失效、经 refresh 静默续期，收尾时须把新令牌写入响应 Cookie */
  renewed: AuthTokens | null;
}

/**
 * 从请求中解析当前登录用户；未登录返回 null。
 * access 失效但 refresh 有效时自动静默续期（不撤销会话，并发请求互不失效），
 * 调用方在返回响应前用 {@link applyRenewedCookies} 把新令牌写入 Cookie
 * （2026-09-05 评审 #6：登录过期续期闭环）。
 */
export function requireUserWithRenewal(req: NextRequest): AuthSession | null {
  const auth = getAuthService();
  const { access, refresh } = getTokensFromRequest(req);
  const user = auth.resolveAccessToken(access);
  if (user) return { user, renewed: null };
  const renewed = auth.renewFromRefresh(refresh);
  if (!renewed) return null;
  const renewedUser = auth.resolveAccessToken(renewed.accessToken);
  if (!renewedUser) return null;
  return { user: renewedUser, renewed };
}

/** 兼容旧调用的简单版：只解析当前用户，不处理续期 Cookie */
export function requireUser(req: NextRequest): UserRow | null {
  return requireUserWithRenewal(req)?.user ?? null;
}

/** 收尾：把静默续期产生的新令牌写入响应 Cookie（无续期时原样返回） */
export function applyRenewedCookies<T extends NextResponse>(res: T, session: AuthSession | null): T {
  if (session?.renewed) {
    setAuthCookies(res, session.renewed.accessToken, session.renewed.refreshToken);
  }
  return res;
}

export function handleAuthError(err: unknown): NextResponse {
  if (err instanceof AuthError) {
    return NextResponse.json({ error: err.message }, { status: err.status });
  }
  const msg = err instanceof Error ? err.message : String(err);
  console.error("[auth] unexpected error:", err);
  return NextResponse.json({ error: `服务器错误: ${msg}` }, { status: 500 });
}

export function ok(data: Record<string, unknown>, init?: ResponseInit): NextResponse {
  return NextResponse.json(data, init);
}

export function unauthorized(message = "请先登录"): NextResponse {
  return NextResponse.json({ error: message }, { status: 401 });
}
