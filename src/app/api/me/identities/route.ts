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
 * GET /api/me/identities —— 查看当前账号的全部登录方式（§5.2）
 */
export async function GET(req: NextRequest) {
  const session = requireUserWithRenewal(req);
  if (!session) return unauthorized();
  try {
    const auth = getAuthService();
    return applyRenewedCookies(ok({ identities: auth.listIdentities(session.user.id) }), session);
  } catch (err) {
    return handleAuthError(err);
  }
}
