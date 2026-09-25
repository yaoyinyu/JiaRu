import { NextRequest, NextResponse } from "next/server";
import { getAuthService } from "@/lib/auth/server";
import {
  applyRenewedCookies,
  handleAuthError,
  ok,
  requireUserWithRenewal,
  unauthorized,
} from "@/lib/auth/http";
import { getRateLimiter, resolveClientIp } from "@/lib/rate-limit";

/**
 * POST /api/auth/bind-phone
 * Body: { phone: string, code: string }
 * 给当前账号补绑手机号（非手机号方式注册后，§5.1 合规要求）。
 * 需要先请求手机验证码（/api/auth/request-code）。
 */
export async function POST(req: NextRequest) {
  const session = requireUserWithRenewal(req);
  if (!session) return unauthorized();
  try {
    // 2026-09-24 安全审计修复：按来源 IP 限制绑号频次（默认 10 次 / 10 分钟），
    // 防止利用绑号接口批量探测手机号是否已注册。
    const limited = getRateLimiter().consume("bindPhone", resolveClientIp(req.headers));
    if (!limited.ok) {
      return NextResponse.json(
        { error: "操作过于频繁，请稍后再试" },
        { status: 429, headers: { "Retry-After": String(limited.retryAfterSeconds) } }
      );
    }
    let body: { phone?: unknown; code?: unknown };
    try {
      body = await req.json();
    } catch {
      return NextResponse.json({ error: "请求体不是合法 JSON" }, { status: 400 });
    }
    if (typeof body.phone !== "string" || typeof body.code !== "string") {
      return NextResponse.json({ error: "缺少手机号或验证码" }, { status: 400 });
    }
    const auth = getAuthService();
    await auth.bindPhone(session.user.id, body.phone, body.code);
    return applyRenewedCookies(ok({ ok: true, user: auth.getMe(session.user.id) }), session);
  } catch (err) {
    return handleAuthError(err);
  }
}
