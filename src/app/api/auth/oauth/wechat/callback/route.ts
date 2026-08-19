import { NextRequest, NextResponse } from "next/server";
import { getAuthService } from "@/lib/auth/server";
import { getClientIp, setAuthCookies } from "@/lib/auth/cookies";
import { exchangeWechatCode, getWechatConfig } from "@/lib/auth/wechat";
import { OAUTH_STATE_COOKIE } from "../route";

/**
 * GET /api/auth/oauth/wechat/callback
 * 微信扫码回调：校验 state（防 CSRF）→ code 换 openid → 登录/注册 → 写登录态 Cookie。
 * 登录成功后跳转 /account（新微信用户需补绑手机号，见账号页绑定入口）。
 */
export async function GET(req: NextRequest) {
  const { searchParams } = req.nextUrl;
  const code = searchParams.get("code");
  const state = searchParams.get("state");
  const cookieState = req.cookies.get(OAUTH_STATE_COOKIE)?.value;

  // 校验 state：缺失或不匹配 → 拒绝（防 CSRF，§9.1）
  if (!state || !cookieState || state !== cookieState) {
    return NextResponse.redirect(new URL("/login?error=state_mismatch", req.nextUrl.origin));
  }
  if (!code) {
    return NextResponse.redirect(new URL("/login?error=wechat_canceled", req.nextUrl.origin));
  }

  const cfg = getWechatConfig();
  if (!cfg) {
    return NextResponse.redirect(new URL("/login?error=wechat_not_configured", req.nextUrl.origin));
  }

  try {
    const profile = await exchangeWechatCode(cfg, code);
    const auth = getAuthService();
    const { user, tokens, isNewUser } = auth.wechatLoginOrRegister(profile.openid, {
      ip: getClientIp(req),
    }, { nickname: profile.nickname });

    // 新微信用户没有手机号 → 跳 /account?bind=1 提示补绑
    const target = isNewUser || !user.phone ? "/account?bind=1" : "/account";
    const res = NextResponse.redirect(new URL(target, req.nextUrl.origin));
    setAuthCookies(res, tokens.accessToken, tokens.refreshToken);
    res.cookies.set(OAUTH_STATE_COOKIE, "", { httpOnly: true, sameSite: "lax", path: "/", maxAge: 0 });
    return res;
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    return NextResponse.redirect(new URL(`/login?error=wechat_failed&detail=${encodeURIComponent(msg)}`, req.nextUrl.origin));
  }
}
