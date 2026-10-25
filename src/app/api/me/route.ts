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
 * GET /api/me —— 当前用户档案 + 登录方式 + 偏好（§8）
 * PATCH /api/me —— 更新个人档案：昵称、简介、公开联系方式与头像
 *   Body: { nickname?, bio?, contact?, contactType?, avatar?, ageGroup? }
 *   `bio`/`contact` 传空串清空；`avatar` 传 null 移除头像（https:// 地址或压缩后的 data URL）。
 *   校验失败返回 400 + `{ error }`，未提交的字段保持原值。
 * access 过期时经 refresh 静默续期，并在本响应下发新 Cookie。
 */
export async function GET(req: NextRequest) {
  const session = requireUserWithRenewal(req);
  if (!session) return unauthorized();
  const auth = getAuthService();
  return applyRenewedCookies(ok({ user: auth.getMe(session.user.id) }), session);
}

export async function PATCH(req: NextRequest) {
  const session = requireUserWithRenewal(req);
  if (!session) return unauthorized();
  try {
    let body: {
      nickname?: unknown;
      avatar?: unknown;
      bio?: unknown;
      contact?: unknown;
      contactType?: unknown;
      ageGroup?: unknown;
    };
    try {
      body = await req.json();
    } catch {
      return NextResponse.json({ error: "请求体不是合法 JSON" }, { status: 400 });
    }
    const auth = getAuthService();
    auth.updateProfile(session.user.id, {
      nickname: typeof body.nickname === "string" ? body.nickname : undefined,
      bio: typeof body.bio === "string" ? body.bio : undefined,
      contact: typeof body.contact === "string" ? body.contact : undefined,
      contactType:
        typeof body.contactType === "string" ? body.contactType : body.contactType === null ? null : undefined,
      avatar: typeof body.avatar === "string" ? body.avatar : body.avatar === null ? null : undefined,
      ageGroup: typeof body.ageGroup === "string" ? body.ageGroup : undefined,
    });
    return applyRenewedCookies(ok({ user: auth.getMe(session.user.id) }), session);
  } catch (err) {
    return handleAuthError(err);
  }
}
