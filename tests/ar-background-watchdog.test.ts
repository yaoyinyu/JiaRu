import assert from "node:assert/strict";
import { test } from "node:test";
import { createBackgroundWatchdog } from "../src/lib/ar-background-watchdog.ts";

function harness(stallMs?: number) {
  let clock = 0;
  let activity = 0;
  let callback: (() => void) | null = null;
  let cleared = 0;
  const stalls: number[] = [];
  const stop = createBackgroundWatchdog({
    onStall: () => stalls.push(clock),
    lastActivity: () => activity,
    stallMs,
    now: () => clock,
    setTimer: fn => { callback = fn; return 1; },
    clearTimer: () => { cleared++; },
  });
  return {
    stalls, stop,
    tick(gapMs: number, active = true) {
      clock += gapMs;
      if (active) activity = clock;
      callback?.();
    },
    get cleared() { return cleared; },
  };
}

test("正常前台活动持续时不触发停用", () => {
  const h = harness();
  for (let i = 0; i < 30; i++) h.tick(1000);
  assert.deepEqual(h.stalls, []);
});

test("后台帧呈现停摆（定时器仍运行）触发一次停用", () => {
  const h = harness();
  h.tick(1000);
  h.tick(1000, false);
  h.tick(1000, false);
  h.tick(1000, false);
  h.tick(1000, false);
  h.tick(1000, false);
  h.tick(1000, false);
  assert.equal(h.stalls.length, 1);
  assert.equal(h.stalls[0], 7000);
});

test("阈值边界：等于 stallMs 不触发，超过才触发", () => {
  const h = harness(5000);
  h.tick(5000, false);
  assert.deepEqual(h.stalls, []);
  h.tick(1, false);
  assert.equal(h.stalls.length, 1);
});

test("停止后不再触发且清理定时器", () => {
  const h = harness();
  h.stop();
  h.tick(60000, false);
  assert.deepEqual(h.stalls, []);
  assert.equal(h.cleared, 1);
});