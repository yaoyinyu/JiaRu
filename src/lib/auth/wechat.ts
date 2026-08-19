import { randomUUID } from "node:crypto";
import { AuthError } from "./types.ts";

/**
 * 微信开放平台「网站应用」OAuth 2.0 登录（文档 §5.1 / §9.1）。
 *
 * 流程：
 *  1. 前端跳转授权 URL（扫码）→ 用户同意后微信回调 redirect_uri（带 code + state）；
 *  2. 服务端用 code 换 access_token + openid（state 校验防 CSRF）；
 *  3. 用 openid 查 user_identities(wechat) → 登录或注册（微信仅返回 openid，
 *     不提供手机号，首次登录后必须补绑手机号，见 /account 绑定入口）。
 *
 * 依赖环境变量：WECHAT_APP_ID、WECHAT_APP_SECRET（微信开放平台「网站应用」，
 * 需认证企业主体，300 元/年）。未配置时相关接口返回明确提示。
 */

export interface WechatConfig {
  appId: string;
  appSecret: string;
}

export function getWechatConfig(): WechatConfig | null {
  const appId = process.env.WECHAT_APP_ID;
  const appSecret = process.env.WECHAT_APP_SECRET;
  if (!appId || !appSecret) return null;
  return { appId, appSecret };
}

/** 构造微信扫码授权 URL（state 防 CSRF） */
export function buildWechatAuthUrl(cfg: WechatConfig, redirectUri: string, state: string): string {
  const params = new URLSearchParams({
    appid: cfg.appId,
    redirect_uri: redirectUri,
    response_type: "code",
    scope: "snsapi_login",
    state,
  });
  return `https://open.weixin.qq.com/connect/qrconnect?${params.toString()}#wechat_redirect`;
}

export interface WechatProfile {
  openid: string;
  nickname?: string;
}

/**
 * 用授权 code 换取 openid（并尽力拉取昵称）。
 * @param httpFetch 可注入的 fetch（测试用），默认全局 fetch。
 */
export async function exchangeWechatCode(
  cfg: WechatConfig,
  code: string,
  httpFetch: typeof fetch = fetch
): Promise<WechatProfile> {
  const tokenParams = new URLSearchParams({
    appid: cfg.appId,
    secret: cfg.appSecret,
    code,
    grant_type: "authorization_code",
  });
  let tokenData: Record<string, unknown>;
  try {
    const tokenResp = await httpFetch(`https://api.weixin.qq.com/sns/oauth2/access_token?${tokenParams.toString()}`);
    tokenData = (await tokenResp.json()) as Record<string, unknown>;
  } catch (err) {
    throw new AuthError("wechat_oauth_failed", `微信授权请求失败: ${err instanceof Error ? err.message : String(err)}`, 502);
  }
  if (typeof tokenData.openid !== "string" || !tokenData.openid) {
    throw new AuthError(
      "wechat_oauth_failed",
      `微信授权失败${tokenData.errmsg ? `: ${String(tokenData.errmsg)}` : ""}`,
      401
    );
  }
  const openid = tokenData.openid;

  // 尽力拉取昵称（失败不影响登录）
  let nickname: string | undefined;
  try {
    const userParams = new URLSearchParams({
      access_token: String(tokenData.access_token ?? ""),
      openid,
    });
    const userResp = await httpFetch(`https://api.weixin.qq.com/sns/userinfo?${userParams.toString()}`);
    const userData = (await userResp.json()) as Record<string, unknown>;
    if (typeof userData.nickname === "string" && userData.nickname) {
      nickname = userData.nickname;
    }
  } catch {
    // 忽略：昵称拉取失败不阻断登录
  }
  return { openid, nickname };
}

export function createOauthState(): string {
  return randomUUID();
}
