import assert from "node:assert/strict";
import test from "node:test";
import { createInMemoryUserDb } from "../src/lib/auth/db.ts";
import { createAuthService } from "../src/lib/auth/service.ts";
import { createCaptcha, verifyCaptcha } from "../src/lib/auth/captcha.ts";
import { hashCode, todayString } from "../src/lib/auth/sms.ts";
import { AuthError } from "../src/lib/auth/types.ts";

/**
 * 2026-09-05 评审 #6/#7 修复的行为回归：
 *  - 图形验证码 SVG 不再包含明文答案（<text> 改笔画路径）；
 *  - 验证码发送台账与生命周期分离（消费=标记，不再物理删除）；
 *  - 换绑在事务内一致更新 users.phone 与 phone identity；
 *  - 解绑 phone 同步清空资料，可再绑定；
 *  - refresh 静默续期并发安全（不轮换会话）+ 临近过期滑动重签。
 */

const SECRET = "test-secret-at-least-16-chars";

function makeAuth(options?: { refreshTtlSec?: number }) {
  const db = createInMemoryUserDb();
  const auth = createAuthService(db, { jwtSecret: SECRET, refreshTtlSec: options?.refreshTtlSec });
  return { db, auth };
}

function seedCode(db: ReturnType<typeof createInMemoryUserDb>, phone: string, code = "123456") {
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

function captchaOk() {
  const { id, answer } = createCaptcha();
  return { id, answer };
}

// ── 图形验证码：SVG 不泄露答案 ──

test("captcha svg contains no text nodes and never leaks the answer", () => {
  for (let round = 0; round < 20; round++) {
    const { svg, answer } = createCaptcha();
    // 关键断言：无 <text> 节点——字形全部为 polyline 坐标，解析文本无法得到答案
    assert.ok(!svg.includes("<text"), "SVG 不得包含 <text> 节点");
    assert.ok(!svg.includes("font-family"), "不得残留字体属性");
    // 字母级泄露检查：坐标只含数字与标点，hsl 颜色全小写；
    // 大写字母仅可能出现于 viewBox 属性名（V/B），其余答案字母出现即泄露。
    for (const ch of answer) {
      if (/[0-9]/.test(ch) || ch === "V" || ch === "B") continue;
      assert.ok(!svg.includes(ch), `SVG 泄露答案字符: ${ch}`);
    }
  }
});

test("captcha answer from createCaptcha still verifies (server-side contract intact)", () => {
  const { id, svg, answer } = createCaptcha();
  assert.ok(svg.length > 100);
  assert.ok(answer.length === 4);
  assert.equal(verifyCaptcha(id, answer), true);
});

// ── 验证码消费与发送台账 ──

test("consumed code cannot be reused and send ledger survives login", async () => {
  const { db, auth } = makeAuth();
  const phone = "13100131000";
  seedCode(db, phone);

  // 首次登录成功（消费验证码）
  const first = await auth.phoneCodeLoginOrRegister(phone, "123456", {});
  assert.equal(first.isNewUser, true);

  // 同一条验证码不能重复使用（此前 deleteCode 后重放会走到注册分支）
  await assert.rejects(
    () => auth.phoneCodeLoginOrRegister(phone, "123456", {}),
    (err: unknown) => err instanceof AuthError && err.code === "code_expired"
  );

  // 发送台账保留：countCodesToday 不因成功登录而减少（评审复现：1→0）
  assert.equal(db.countCodesToday(phone, todayString(Date.now())), 1);

  // 60 秒节流依据完整台账：成功登录后立即再发仍被节流（防轰炸保留）
  await assert.rejects(
    () => auth.requestSmsCode(phone, captchaOk()),
    (err: unknown) => err instanceof AuthError && err.code === "code_throttled"
  );
});

// ── 换绑一致性 ──

test("rebind updates users.phone and identity together; old phone becomes free", async () => {
  const { db, auth } = makeAuth();
  const a = auth.wechatLoginOrRegister("openid-rebind-1", {});

  seedCode(db, "13400134000");
  await auth.bindPhone(a.user.id, "13400134000", "123456");

  // 换绑新号
  seedCode(db, "13300133000");
  await auth.bindPhone(a.user.id, "13300133000", "123456");

  // 资料与身份一致：都是新号
  assert.equal(auth.getMe(a.user.id).user.phone, "13300133000");
  const phoneIdentity = auth.listIdentities(a.user.id).find((i) => i.provider === "phone");
  assert.equal(phoneIdentity?.identifier, "13300133000");

  // 新号登录同一账号（此前复现：UNIQUE constraint failed: users.phone）
  seedCode(db, "13300133000");
  const byNew = await auth.phoneCodeLoginOrRegister("13300133000", "123456", {});
  assert.equal(byNew.isNewUser, false);
  assert.equal(byNew.user.id, a.user.id);

  // 旧号释放：可注册为全新账号，而不是登录回 A
  seedCode(db, "13400134000");
  const byOld = await auth.phoneCodeLoginOrRegister("13400134000", "123456", {});
  assert.equal(byOld.isNewUser, true);
  assert.notEqual(byOld.user.id, a.user.id);
});

// ── 解绑一致性 ──

test("unbind phone clears profile phone and allows binding again", async () => {
  const { db, auth } = makeAuth();
  const w = auth.wechatLoginOrRegister("openid-unbind-2", {});

  seedCode(db, "13200132000");
  await auth.bindPhone(w.user.id, "13200132000", "123456");

  // 还有 wechat 一种方式 → 允许解绑 phone
  auth.removeIdentity(w.user.id, "phone");
  assert.deepEqual(auth.listIdentities(w.user.id).map((i) => i.provider), ["wechat"]);
  // 资料同步清空（此前残留 users.phone 会让同号再绑触发 UNIQUE 冲突）
  assert.equal(auth.getMe(w.user.id).user.phone, null);

  // 解绑后可重新绑定（含同一号码）
  seedCode(db, "13200132000");
  await auth.bindPhone(w.user.id, "13200132000", "123456");
  assert.equal(auth.getMe(w.user.id).user.phone, "13200132000");
});

// ── refresh 静默续期 ──

test("renewFromRefresh issues working access token without rotating session", async () => {
  const { auth } = makeAuth();
  const { user, tokens } = auth.wechatLoginOrRegister("openid-renew-1", {});

  const renewed = auth.renewFromRefresh(tokens.refreshToken);
  assert.ok(renewed, "refresh 有效时应可续期");
  assert.equal(auth.resolveAccessToken(renewed.accessToken)?.id, user.id);

  // 并发安全：旧 refresh 不被撤销，可再次续期（对比 rotateTokens 的轮换语义）
  assert.equal(auth.resolveAccessToken(tokens.accessToken)?.id, user.id);
  const again = auth.renewFromRefresh(tokens.refreshToken);
  assert.ok(again);
  assert.equal(auth.resolveAccessToken(again!.accessToken)?.id, user.id);

  // 长寿命 refresh 不滑动重签（剩余 > 15 天）
  assert.equal(renewed.refreshToken, tokens.refreshToken);

  // 注销后不可续期
  auth.logout(tokens.refreshToken, {});
  assert.equal(auth.renewFromRefresh(tokens.refreshToken), null);
  assert.equal(auth.renewFromRefresh(undefined), null);
  assert.equal(auth.renewFromRefresh("garbage"), null);
});

test("renewFromRefresh slides refresh forward when close to expiry", (t) => {
  // JWT payload 无随机成分（iat/exp 均为秒级时钟），登录与续期同秒时
  // 重签结果与原 token 字节级相同，真实时钟下 notEqual 断言依赖秒边界
  // 碰运气 → 用 mock 时钟确定性构造"临近过期"场景。
  t.mock.timers.enable({ apis: ["Date"] });
  const { auth } = makeAuth({ refreshTtlSec: 3600 }); // 1 小时 << 15 天阈值
  const { user, tokens } = auth.wechatLoginOrRegister("openid-slide-1", {});

  // 前进 30 分钟：refresh 剩余 30 分钟 < 15 天阈值，但尚未过期 → 应滑动重签
  t.mock.timers.tick(30 * 60 * 1000);
  const renewed = auth.renewFromRefresh(tokens.refreshToken);
  assert.ok(renewed);
  assert.notEqual(renewed.refreshToken, tokens.refreshToken, "临近过期应滑动重签 refresh");
  assert.equal(auth.resolveAccessToken(renewed.accessToken)?.id, user.id);
  assert.ok(auth.resolveRefreshToken(renewed.refreshToken), "重签后的 refresh 仍然有效");
});
