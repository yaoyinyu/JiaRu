import { NextRequest, NextResponse } from "next/server";
import { getAuthService } from "@/lib/auth/server";
import { handleAuthError, ok, requireUser, unauthorized } from "@/lib/auth/http";

/**
 * GET /api/me —— 当前用户档案 + 登录方式 + 偏好（§8）
 * PATCH /api/me —— 更新昵称/头像（Body: { nickname? }）
 */
export async function GET(req: NextRequest) {
  const user = requireUser(req);
  if (!user) return unauthorized();
  const auth = getAuthService();
  return ok({ user: auth.getMe(user.id) });
}

export async function PATCH(req: NextRequest) {
  const user = requireUser(req);
  if (!user) return unauthorized();
  try {
    let body: { nickname?: unknown; avatar?: unknown; ageGroup?: unknown };
    try {
      body = await req.json();
    } catch {
      return NextResponse.json({ error: "请求体不是合法 JSON" }, { status: 400 });
    }
    const auth = getAuthService();
    auth.updateProfile(user.id, {
      nickname: typeof body.nickname === "string" ? body.nickname : undefined,
      avatar: typeof body.avatar === "string" ? body.avatar : undefined,
      ageGroup: typeof body.ageGroup === "string" ? body.ageGroup : undefined,
    });
    return ok({ user: auth.getMe(user.id) });
  } catch (err) {
    return handleAuthError(err);
  }
}
