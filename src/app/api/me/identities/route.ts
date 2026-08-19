import { NextRequest } from "next/server";
import { getAuthService } from "@/lib/auth/server";
import { handleAuthError, ok, requireUser, unauthorized } from "@/lib/auth/http";

/**
 * GET /api/me/identities —— 查看当前账号的全部登录方式（§5.2）
 */
export async function GET(req: NextRequest) {
  const user = requireUser(req);
  if (!user) return unauthorized();
  try {
    const auth = getAuthService();
    return ok({ identities: auth.listIdentities(user.id) });
  } catch (err) {
    return handleAuthError(err);
  }
}
