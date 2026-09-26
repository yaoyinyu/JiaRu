import assert from "node:assert/strict";
import test from "node:test";
import {
  AI_QUOTA_DEFAULTS,
  createAiQuotaGuard,
  guestIdentityFromHeaders,
  quotaDayString,
  type Reservation,
} from "../src/lib/ai-quota.ts";

/** 固定起始时刻（本地 2026-09-14 10:00:00） */
const BASE_MS = new Date(2026, 8, 14, 10, 0, 0, 0).getTime();

function makeGuard(env: Record<string, string> = {}, startMs = BASE_MS) {
  let nowMs = startMs;
  const guard = createAiQuotaGuard({
    now: () => nowMs,
    env,
  });
  return {
    guard,
    advanceHours(h: number) {
      nowMs += h * 3600 * 1000;
    },
  };
}

function reserveOk(
  guard: ReturnType<typeof createAiQuotaGuard>,
  identity: string,
  authenticated = false
): Reservation {
  const result = guard.reserve({ identity, authenticated, engine: "agnes" });
  assert.equal(result.ok, true, `reserve should pass for ${identity}`);
  return (result as { ok: true; reservation: Reservation }).reservation;
}

function reserveFail(
  guard: ReturnType<typeof createAiQuotaGuard>,
  identity: string,
  authenticated = false
) {
  const result = guard.reserve({ identity, authenticated, engine: "agnes" });
  assert.equal(result.ok, false, `reserve should be denied for ${identity}`);
  return result as { ok: false; status: 429; error: string; retryAfterSeconds: number };
}

test("quotaDayString formats local calendar day", () => {
  assert.equal(quotaDayString(new Date(2026, 8, 14, 10, 0, 0).getTime()), "2026-09-14");
  assert.equal(quotaDayString(new Date(2026, 0, 1, 0, 0, 0).getTime()), "2026-01-01");
});

test("guest daily limit defaults and denies with retry-after until next day", () => {
  const { guard, advanceHours } = makeGuard();
  for (let i = 0; i < AI_QUOTA_DEFAULTS.guestDaily; i++) {
    const r = reserveOk(guard, "guest:aaaa");
    guard.commit(r); // 每次请求即时完成，释放并发名额（并发是独立测试）
  }
  const denied = reserveFail(guard, "guest:aaaa");
  assert.equal(denied.status, 429);
  assert.match(denied.error, /今日生成次数已用完/);
  assert.ok(denied.retryAfterSeconds > 0 && denied.retryAfterSeconds <= 24 * 3600);

  // 快进 1 小时（仍同一天）→ 仍拒绝；再快进跨过午夜 → 恢复
  advanceHours(1);
  assert.equal(reserveFail(guard, "guest:aaaa").ok, false);
  advanceHours(14); // 10:00 + 15h = 次日 01:00
  reserveOk(guard, "guest:aaaa");
});

test("authenticated users get the higher daily limit", () => {
  const { guard } = makeGuard();
  for (let i = 0; i < AI_QUOTA_DEFAULTS.userDaily; i++) {
    const r = reserveOk(guard, "user:u1", true);
    guard.commit(r);
  }
  const denied = reserveFail(guard, "user:u1", true);
  assert.match(denied.error, /今日生成次数已用完/);
  // 游客额度不受登录用户消耗影响
  reserveOk(guard, "guest:bbbb");
});

test("global daily budget breaker denies everyone once exhausted", () => {
  const { guard } = makeGuard({ AI_QUOTA_GLOBAL_DAILY: "3" });
  reserveOk(guard, "guest:a1");
  reserveOk(guard, "guest:a2");
  reserveOk(guard, "user:u1", true);
  const denied = reserveFail(guard, "user:u2", true);
  assert.match(denied.error, /全局上限/);
  const deniedGuest = reserveFail(guard, "guest:a3");
  assert.match(deniedGuest.error, /全局上限/);
});

test("global concurrency limit blocks the second in-flight request and commit releases it", () => {
  const { guard } = makeGuard({ AI_QUOTA_GLOBAL_CONCURRENCY: "1" });
  const first = reserveOk(guard, "guest:a1");
  const denied = reserveFail(guard, "guest:a2");
  assert.match(denied.error, /并发上限/);
  guard.commit(first);
  // commit 释放在飞名额 → 下一个身份可以 reserve
  reserveOk(guard, "guest:a2");
});

test("same identity cannot run two generations at once", () => {
  const { guard } = makeGuard();
  const first = reserveOk(guard, "guest:a1");
  const denied = reserveFail(guard, "guest:a1");
  assert.match(denied.error, /正在进行/);
  guard.commit(first);
  reserveOk(guard, "guest:a1");
});

test("release returns the identity daily count but keeps the global count", () => {
  const { guard } = makeGuard({ AI_QUOTA_GUEST_DAILY: "1", AI_QUOTA_GLOBAL_DAILY: "100" });
  const only = reserveOk(guard, "guest:a1");
  assert.equal(reserveFail(guard, "guest:a1").ok, false);
  guard.release(only);
  // 身份额度已返还 → 可再次预留
  const second = reserveOk(guard, "guest:a1");
  // 全局计数保留 2（首次失败 + 本次成功），失败无法刷穿全局预算
  assert.equal(guard.snapshot().globalCount, 2);
  guard.commit(second);
  assert.equal(guard.snapshot().globalCount, 2);
  assert.equal(guard.snapshot().globalInFlight, 0);
});

test("release across a day boundary does not resurrect yesterday's counts", () => {
  const { guard, advanceHours } = makeGuard();
  const r = reserveOk(guard, "guest:a1");
  advanceHours(15); // 跨天
  guard.release(r);
  const snap = guard.snapshot();
  assert.equal(snap.globalCount, 0, "day rolled: global count reset");
  assert.equal(snap.identityCounts["guest:a1"] ?? 0, 0);
});

test("invalid env values fall back to defaults", () => {
  const { guard } = makeGuard({
    AI_QUOTA_GUEST_DAILY: "not-a-number",
    AI_QUOTA_USER_DAILY: "0",
    AI_QUOTA_GLOBAL_DAILY: "-5",
    AI_QUOTA_GLOBAL_CONCURRENCY: "abc",
  });
  // 回退默认：游客 5 次（每次即时完成释放并发名额）
  for (let i = 0; i < AI_QUOTA_DEFAULTS.guestDaily; i++) {
    const r = reserveOk(guard, "guest:a1");
    guard.commit(r);
  }
  assert.equal(reserveFail(guard, "guest:a1").ok, false);
});

test("guestIdentityFromHeaders 默认不采信伪造代理头", () => {
  const fromIp1 = guestIdentityFromHeaders({ get: (n) => (n === "x-forwarded-for" ? "203.0.113.7, 70.41.3.25" : null) });
  const fromIp2 = guestIdentityFromHeaders({ get: (n) => (n === "x-forwarded-for" ? "198.51.100.9" : null) });
  const fromMissing = guestIdentityFromHeaders({ get: () => null });
  assert.match(fromIp1, /^guest:[0-9a-f]{16}$/);
  assert.match(fromMissing, /^guest:[0-9a-f]{16}$/);
  // 未声明可信代理时，改一个 XFF 不能换到一份独立额度（M5：伪造即共享桶）
  assert.equal(fromIp1, fromIp2);
  assert.equal(fromIp1, fromMissing);
});

test("guestIdentityFromHeaders 在 JIARU_TRUST_PROXY=1 下按真实来源分桶", () => {
  const env = { JIARU_TRUST_PROXY: "1" };
  const real1 = guestIdentityFromHeaders({ get: (n) => (n === "x-real-ip" ? "203.0.113.7" : null) }, env);
  const real2 = guestIdentityFromHeaders({ get: (n) => (n === "x-real-ip" ? "198.51.100.9" : null) }, env);
  assert.match(real1, /^guest:[0-9a-f]{16}$/);
  assert.notEqual(real1, real2, "反代注入的 X-Real-IP 应产生不同身份");
});
