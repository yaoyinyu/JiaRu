import assert from "node:assert/strict";
import test from "node:test";
import { createInMemoryUserDb, type UserDb } from "../src/lib/auth/db.ts";
import { createAuthService } from "../src/lib/auth/service.ts";
import { createCaptcha } from "../src/lib/auth/captcha.ts";
import { buildWechatAuthUrl, exchangeWechatCode, getWechatConfig } from "../src/lib/auth/wechat.ts";
import { hashCode, todayString } from "../src/lib/auth/sms.ts";
import { AuthError } from "../src/lib/auth/types.ts";

const SECRET = "test-secret-at-least-16-chars";

function makeAuth() {
  const db = createInMemoryUserDb();
  const auth = createAuthService(db, { jwtSecret: SECRET });
  return { db, auth };
}

/** 直接种入一条未过期的验证码（绕过 60s 节流，验证码 5 分钟有效） */
function seedCode(db: UserDb, phone: string, code = "123456") {
  db.insertCode({
    phone,
    purpose: "login",
    code_hash: hashCode(code),
    expires_at: Date.now() + 5 * 60 * 1000,
    attempts: 0,
    created_at: Date.now(),
    day: todayString(Date.now()),
  });
}

/** 生成一个已通过人机验证的请求参数（先创建图形验证码） */
function captchaOk() {
  const { id, answer } = createCaptcha();
  return { id, answer };
}

// ── 手机号登录 ──

test("phone code request requires captcha and throttles at 60s", async () => {
  const { auth } = makeAuth();
  // 无人机验证：直接拒绝，不发送
  await assert.rejects(
    () => auth.requestSmsCode("13800138000", { id: "no-such-id", answer: "XXXX" }),
    (err: unknown) => err instanceof AuthError && err.code === "captcha_failed"
  );
  // 图形验证码错误
  await assert.rejects(
    () => auth.requestSmsCode("13800138000", { id: captchaOk().id, answer: "ZZZZ" }),
    (err: unknown) => err instanceof AuthError && err.code === "captcha_failed"
  );
  // 验证码正确：发送成功并返回 devCode
  const first = await auth.requestSmsCode("13800138000", captchaOk());
  assert.ok(first.devCode, "dev 模式应返回 devCode");
  assert.match(first.devCode!, /^\d{6}$/);

  // 60 秒节流仍然生效
  await assert.rejects(
    () => auth.requestSmsCode("13800138000", captchaOk()),
    (err: unknown) => err instanceof AuthError && err.status === 429
  );
});

test("phone code login-or-register works with correct code", async () => {
  const { db, auth } = makeAuth();
  seedCode(db, "13900139000");
  const { user, isNewUser } = await auth.phoneCodeLoginOrRegister("13900139000", "123456", {});
  assert.equal(isNewUser, true);
  assert.equal(user.phone, "13900139000");

  // 再次登录：同一账号
  seedCode(db, "13900139000");
  const second = await auth.phoneCodeLoginOrRegister("13900139000", "123456", {});
  assert.equal(second.isNewUser, false);
  assert.equal(second.user.id, user.id);
});

test("phone code rejects wrong codes and locks after 5 attempts", async () => {
  const { db, auth } = makeAuth();
  seedCode(db, "13700137000");
  for (let i = 0; i < 5; i++) {
    await assert.rejects(
      () => auth.phoneCodeLoginOrRegister("13700137000", "000000", {}),
      (err: unknown) => err instanceof AuthError && err.status === 401
    );
  }
  // 第 6 次：尝试次数超限 → 429
  await assert.rejects(
    () => auth.phoneCodeLoginOrRegister("13700137000", "000000", {}),
    (err: unknown) => err instanceof AuthError && err.status === 429
  );
});

// ── 微信登录 ──

test("wechat login-or-register creates account without phone (needs bind)", async () => {
  const { auth } = makeAuth();
  const { user, tokens, isNewUser } = auth.wechatLoginOrRegister(
    "openid-abcdef123456",
    {},
    { nickname: "小明" }
  );
  assert.equal(isNewUser, true);
  assert.equal(user.phone, null, "微信仅返回 openid，新账号无手机号");
  assert.equal(user.nickname, "小明");
  assert.ok(tokens.accessToken && tokens.refreshToken);

  // 登录方式只有 wechat
  const identities = auth.listIdentities(user.id);
  assert.deepEqual(identities.map((i) => i.provider), ["wechat"]);
});

test("wechat second login returns same account (no new user)", async () => {
  const { auth } = makeAuth();
  const first = auth.wechatLoginOrRegister("openid-xyz789", {});
  const second = auth.wechatLoginOrRegister("openid-xyz789", {}, { nickname: "忽略首次昵称" });
  assert.equal(second.isNewUser, false);
  assert.equal(second.user.id, first.user.id);
});

test("wechat account can bind phone then login by phone", async () => {
  const { db, auth } = makeAuth();
  const { user } = auth.wechatLoginOrRegister("openid-bind-001", {});
  assert.equal(user.phone, null);

  // 补绑手机号
  seedCode(db, "13600136000");
  await auth.bindPhone(user.id, "13600136000", "123456");
  assert.equal(auth.getMe(user.id).user.phone, "13600136000");

  // 手机号登录同一账号（微信绑定后手机号可登录）
  seedCode(db, "13600136000");
  const byPhone = await auth.phoneCodeLoginOrRegister("13600136000", "123456", {});
  assert.equal(byPhone.user.id, user.id);
  assert.deepEqual(auth.listIdentities(user.id).map((i) => i.provider).sort(), ["phone", "wechat"]);
});

test("wechat openid is validated", () => {
  const { auth } = makeAuth();
  assert.throws(() => auth.wechatLoginOrRegister("short", {}), AuthError);
});

test("wechat oauth helpers build auth url and exchange code", async () => {
  const cfg = { appId: "wx-app-id", appSecret: "wx-app-secret" };
  const url = buildWechatAuthUrl(cfg, "https://example.com/api/auth/oauth/wechat/callback", "state-123");
  assert.ok(url.startsWith("https://open.weixin.qq.com/connect/qrconnect?"));
  assert.ok(url.includes("appid=wx-app-id"));
  assert.ok(url.includes("state=state-123"));
  assert.ok(url.includes("redirect_uri="));

  // 未配置环境变量 → getWechatConfig 返回 null
  const savedId = process.env.WECHAT_APP_ID;
  const savedSecret = process.env.WECHAT_APP_SECRET;
  delete process.env.WECHAT_APP_ID;
  delete process.env.WECHAT_APP_SECRET;
  try {
    assert.equal(getWechatConfig(), null);
  } finally {
    if (savedId !== undefined) process.env.WECHAT_APP_ID = savedId;
    if (savedSecret !== undefined) process.env.WECHAT_APP_SECRET = savedSecret;
  }

  // code 换 openid（注入 fake fetch）
  const fakeFetch = (async (url: string) => {
    if (url.includes("oauth2/access_token")) {
      return new Response(JSON.stringify({ access_token: "at", openid: "openid-from-wx", scope: "snsapi_login" }));
    }
    if (url.includes("sns/userinfo")) {
      return new Response(JSON.stringify({ openid: "openid-from-wx", nickname: "微信昵称" }));
    }
    return new Response("{}");
  }) as unknown as typeof fetch;
  const profile = await exchangeWechatCode(cfg, "code-1", fakeFetch);
  assert.equal(profile.openid, "openid-from-wx");
  assert.equal(profile.nickname, "微信昵称");
});

// ── 会话与令牌 ──

test("access token resolves current user; revoked session invalidates", async () => {
  const { auth } = makeAuth();
  const { user, tokens } = auth.wechatLoginOrRegister("openid-session-1", {});

  const resolved = auth.resolveAccessToken(tokens.accessToken);
  assert.equal(resolved?.id, user.id);
  assert.equal(auth.resolveAccessToken("garbage"), null);
  assert.equal(auth.resolveAccessToken(null), null);

  // 注销会话后 access token 失效
  auth.logout(tokens.refreshToken, {});
  assert.equal(auth.resolveAccessToken(tokens.accessToken), null);
});

test("refresh token rotation issues new working tokens", async () => {
  const { auth } = makeAuth();
  const { user, tokens } = auth.wechatLoginOrRegister("openid-rot-1", {});

  const rotated = auth.rotateTokens(tokens.refreshToken, {});
  assert.ok(rotated);
  assert.equal(auth.resolveAccessToken(rotated.accessToken)?.id, user.id);
  // 旧 refresh 已吊销
  assert.equal(auth.rotateTokens(tokens.refreshToken, {}), null);
});

test("unbind identity keeps at least one method", async () => {
  const { db, auth } = makeAuth();
  const { user } = auth.wechatLoginOrRegister("openid-unbind-1", {});

  // 只有微信一种方式，不能解绑
  assert.throws(() => auth.removeIdentity(user.id, "wechat"), AuthError);

  // 补绑手机号后再解绑微信
  seedCode(db, "13600136000");
  await auth.bindPhone(user.id, "13600136000", "123456");
  auth.removeIdentity(user.id, "wechat");
  assert.deepEqual(auth.listIdentities(user.id).map((i) => i.provider), ["phone"]);
});

test("bind phone rejects a phone owned by another account", async () => {
  const { db, auth } = makeAuth();
  const a = auth.wechatLoginOrRegister("openid-a-1", {});
  const b = auth.wechatLoginOrRegister("openid-b-1", {});

  seedCode(db, "13500135000");
  await auth.bindPhone(a.user.id, "13500135000", "123456");

  // b 尝试绑定已被 a 占用的手机号 → 409（先于验证码校验）
  await assert.rejects(
    () => auth.bindPhone(b.user.id, "13500135000", "000000"),
    (err: unknown) => err instanceof AuthError && err.status === 409
  );
});

test("update profile and improvement preference persist", async () => {
  const { auth } = makeAuth();
  const { user } = auth.wechatLoginOrRegister("openid-profile-1", {});

  auth.updateProfile(user.id, { nickname: "小美" });
  assert.equal(auth.getMe(user.id).user.nickname, "小美");

  auth.setImprovementPreference(user.id, false);
  assert.equal(auth.getMe(user.id).consent.improvementEnabled, false);
  auth.setImprovementPreference(user.id, true);
  assert.equal(auth.getMe(user.id).consent.improvementEnabled, true);
});
