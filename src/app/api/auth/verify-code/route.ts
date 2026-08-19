import { NextRequest, NextResponse } from "next/server";
import { getAuthService } from "@/lib/auth/server";
import { getClientIp, setAuthCookies } from "@/lib/auth/cookies";
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
