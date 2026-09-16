import { NextRequest, NextResponse } from "next/server";
import { getAuthService } from "@/lib/auth/server";
import {
  applyRenewedCookies,
  handleAuthError,
  ok,
  requireUserWithRenewal,
  unauthorized,
} from "@/lib/auth/http";

/**
 * PATCH /api/me/improvement
 * Body: { enabled: boolean }
 * 账号级「用户改进计划」偏好（§5.6，联动浏览器 localStorage）。
 */
export async function PATCH(req: NextRequest) {
  const session = requireUserWithRenewal(req);
  if (!session) return unauthorized();
  try {
    let body: { enabled?: unknown };
    try {
      body = await req.json();
    } catch {
      return NextResponse.json({ error: "请求体不是合法 JSON" }, { status: 400 });
    }
    if (typeof body.enabled !== "boolean") {
      return NextResponse.json({ error: "缺少 enabled 布尔值" }, { status: 400 });
    }
    const auth = getAuthService();
    auth.setImprovementPreference(session.user.id, body.enabled);
    return applyRenewedCookies(ok({ improvementEnabled: body.enabled }), session);
  } catch (err) {
    return handleAuthError(err);
  }
}
