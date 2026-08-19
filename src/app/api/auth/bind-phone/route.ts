import { NextRequest, NextResponse } from "next/server";
import { getAuthService } from "@/lib/auth/server";
import { handleAuthError, ok, requireUser, unauthorized } from "@/lib/auth/http";

/**
 * POST /api/auth/bind-phone
 * Body: { phone: string, code: string }
 * 给当前账号补绑手机号（非手机号方式注册后，§5.1 合规要求）。
 * 需要先请求手机验证码（/api/auth/request-code）。
 */
export async function POST(req: NextRequest) {
  const user = requireUser(req);
  if (!user) return unauthorized();
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
    await auth.bindPhone(user.id, body.phone, body.code);
    return ok({ ok: true, user: auth.getMe(user.id) });
  } catch (err) {
    return handleAuthError(err);
  }
}
