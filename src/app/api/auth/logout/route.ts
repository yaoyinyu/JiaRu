import { NextRequest, NextResponse } from "next/server";
import { getAuthService } from "@/lib/auth/server";
import { clearAuthCookies, getClientIp, getTokensFromRequest } from "@/lib/auth/cookies";

/**
 * POST /api/auth/logout
 * 注销当前会话（撤销 refresh token 对应 session，清空 Cookie）。
 */
export async function POST(req: NextRequest) {
  const auth = getAuthService();
  const { refresh } = getTokensFromRequest(req);
  auth.logout(refresh, { ip: getClientIp(req) });
  const res = NextResponse.json({ ok: true });
  clearAuthCookies(res);
  return res;
}
