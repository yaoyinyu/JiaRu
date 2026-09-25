import { NextRequest, NextResponse } from "next/server";
import { getAuthService } from "@/lib/auth/server";
import { getClientIp, setAuthCookies } from "@/lib/auth/cookies";
import { getRateLimiter, resolveClientIp } from "@/lib/rate-limit";
import { handleAuthError, ok } from "@/lib/auth/http";

/**
 * POST /api/auth/verify-code
 * Body: { phone: string, code: string }
 * 手机号验证码登录/注册（登录即注册，文档 §5.1）。
 */
export async function POST(req: NextRequest) {
  try {
    let body: { phone?: unknown; code?: unknown };
    try {
      body = await req.json();
    } catch {
      return NextResponse.json({ error: "请求体不是合法 JSON" }, { status: 400 });
    }
    if (typeof body.phone !== "string" || typeof body.code !== "string") {
      return NextResponse.json({ error: "缺少手机号或验证码" }, { status: 400 });
    }

    // 2026-09-24 安全审计修复：按来源 IP 限制验证码校验频次（默认 20 次 / 10 分钟）
    const limited = getRateLimiter().consume("verifyCode", resolveClientIp(req.headers));
    if (!limited.ok) {
      return NextResponse.json(
        { error: "操作过于频繁，请稍后再试" },
        { status: 429, headers: { "Retry-After": String(limited.retryAfterSeconds) } }
      );
    }

    const auth = getAuthService();
    const { user, tokens, isNewUser } = await auth.phoneCodeLoginOrRegister(body.phone, body.code, {
      ip: getClientIp(req),
    });

    const res = ok({ user: auth.getMe(user.id), isNewUser });
    setAuthCookies(res, tokens.accessToken, tokens.refreshToken);
    return res;
  } catch (err) {
    return handleAuthError(err);
  }
}
