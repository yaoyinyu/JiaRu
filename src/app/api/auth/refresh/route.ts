import { NextRequest, NextResponse } from "next/server";
import { getAuthService } from "@/lib/auth/server";
import { clearAuthCookies, getTokensFromRequest, setAuthCookies } from "@/lib/auth/cookies";
import { handleAuthError, ok } from "@/lib/auth/http";

/**
 * POST /api/auth/refresh
 * 静默续期：refresh cookie 有效 → 换发新 access（并发安全，不轮换会话），
 * refresh 剩余不足 15 天时顺带滑动重签。失败清除 Cookie 并返回 401。
 * 前端也可主动调用；多数场景由 requireUser 在 access 失效时自动完成。
 */
export async function POST(req: NextRequest) {
  try {
    const { refresh } = getTokensFromRequest(req);
    const auth = getAuthService();
    const renewed = auth.renewFromRefresh(refresh);
    if (!renewed) {
      const res = NextResponse.json({ error: "登录已过期，请重新登录" }, { status: 401 });
      clearAuthCookies(res);
      return res;
    }
    const res = ok({ ok: true });
    setAuthCookies(res, renewed.accessToken, renewed.refreshToken);
    return res;
  } catch (err) {
    return handleAuthError(err);
  }
}
