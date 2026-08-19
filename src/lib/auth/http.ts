import { NextRequest, NextResponse } from "next/server";
import { getAuthService } from "./server.ts";
import { getTokensFromRequest } from "./cookies.ts";
import { AuthError, type UserRow } from "./types.ts";

/**
 * 认证相关 Route Handler 共享工具。
 */

/** 从请求中解析当前登录用户（access token → 会话 → 用户）；未登录返回 null */
export function requireUser(req: NextRequest): UserRow | null {
  const auth = getAuthService();
  const { access } = getTokensFromRequest(req);
  return auth.resolveAccessToken(access);
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
