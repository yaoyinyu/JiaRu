import { NextRequest } from "next/server";
import { getAuthService } from "@/lib/auth/server";
import { handleAuthError, ok, requireUser, unauthorized } from "@/lib/auth/http";

/**
 * DELETE /api/me/identities/:provider —— 解绑某登录方式（至少保留一种，§5.2）
 * provider: phone | email | wechat | github
 */
export async function DELETE(
  req: NextRequest,
  ctx: { params: Promise<{ provider: string }> }
) {
  const user = requireUser(req);
  if (!user) return unauthorized();
  try {
    const { provider } = await ctx.params;
    const auth = getAuthService();
    auth.removeIdentity(user.id, provider);
    return ok({ ok: true, identities: auth.listIdentities(user.id) });
  } catch (err) {
    return handleAuthError(err);
  }
}
