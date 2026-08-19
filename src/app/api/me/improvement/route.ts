import { NextRequest, NextResponse } from "next/server";
import { getAuthService } from "@/lib/auth/server";
import { handleAuthError, ok, requireUser, unauthorized } from "@/lib/auth/http";

/**
 * PATCH /api/me/improvement
 * Body: { enabled: boolean }
 * 账号级「用户改进计划」偏好（§5.6，联动浏览器 localStorage）。
 */
export async function PATCH(req: NextRequest) {
  const user = requireUser(req);
  if (!user) return unauthorized();
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
    auth.setImprovementPreference(user.id, body.enabled);
    return ok({ improvementEnabled: body.enabled });
  } catch (err) {
    return handleAuthError(err);
  }
}
