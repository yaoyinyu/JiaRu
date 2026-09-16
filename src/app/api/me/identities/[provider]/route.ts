import { NextRequest } from "next/server";
import { getAuthService } from "@/lib/auth/server";
import {
  applyRenewedCookies,
  handleAuthError,
  ok,
  requireUserWithRenewal,
  unauthorized,
} from "@/lib/auth/http";

/**
 * DELETE /api/me/identities/:provider —— 解绑某登录方式（至少保留一种，§5.2）
 * provider: phone | email | wechat | github
 */
export async function DELETE(
  req: NextRequest,
  ctx: { params: Promise<{ provider: string }> }
) {
  const session = requireUserWithRenewal(req);
  if (!session) return unauthorized();
  try {
    const { provider } = await ctx.params;
    const auth = getAuthService();
    auth.removeIdentity(session.user.id, provider);
    return applyRenewedCookies(ok({ ok: true, identities: auth.listIdentities(session.user.id) }), session);
  } catch (err) {
    return handleAuthError(err);
  }
}
