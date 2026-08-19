import { NextRequest, NextResponse } from "next/server";
import { getAuthService } from "@/lib/auth/server";
import { handleAuthError, ok } from "@/lib/auth/http";

/**
 * POST /api/auth/request-code
 * Body: { phone: string, captchaId: string, captchaAnswer: string }
 * 请求手机验证码。必须先通过人机验证（图形验证码）：
 *  - captchaId/captchaAnswer 来自 GET /api/auth/captcha；
 *  - 未通过人机验证 → 400，不发送短信；
 *  - 通过后仍受 60 秒节流、单日 10 条限制（§5.1）。
 * 开发模式（未配置短信服务商）返回 devCode 便于本地联调。
 */
export async function POST(req: NextRequest) {
  try {
    let body: { phone?: unknown; captchaId?: unknown; captchaAnswer?: unknown };
    try {
      body = await req.json();
    } catch {
      return NextResponse.json({ error: "请求体不是合法 JSON" }, { status: 400 });
    }
    if (typeof body.phone !== "string") {
      return NextResponse.json({ error: "缺少手机号" }, { status: 400 });
    }
    if (typeof body.captchaId !== "string" || typeof body.captchaAnswer !== "string") {
      return NextResponse.json({ error: "请先完成人机验证" }, { status: 400 });
    }

    const auth = getAuthService();
    const { devCode } = await auth.requestSmsCode(body.phone, {
      id: body.captchaId,
      answer: body.captchaAnswer,
    });
    return ok(devCode ? { sent: true, devCode } : { sent: true });
  } catch (err) {
    return handleAuthError(err);
  }
}
