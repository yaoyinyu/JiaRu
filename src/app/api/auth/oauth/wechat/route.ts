import { NextRequest, NextResponse } from "next/server";
import { buildWechatAuthUrl, createOauthState, getWechatConfig } from "@/lib/auth/wechat";

export const OAUTH_STATE_COOKIE = "jiaru_oauth_state";

/**
 * GET /api/auth/oauth/wechat
 * 发起微信扫码登录：未配置 → 503 提示；已配置 → 302 跳转微信授权页
 * （state 存 httpOnly Cookie，回调时校验防 CSRF，§9.1）。
 */
export async function GET(req: NextRequest) {
  const cfg = getWechatConfig();
  if (!cfg) {
    return NextResponse.json(
      { error: "微信登录尚未配置（需要 WECHAT_APP_ID / WECHAT_APP_SECRET，微信开放平台企业认证）" },
      { status: 503 }
    );
  }
  const origin = req.nextUrl.origin;
  const redirectUri = `${origin}/api/auth/oauth/wechat/callback`;
  const state = createOauthState();

  const res = NextResponse.redirect(buildWechatAuthUrl(cfg, redirectUri, state));
  res.cookies.set(OAUTH_STATE_COOKIE, state, {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: 10 * 60, // 10 分钟有效
  });
  return res;
}
