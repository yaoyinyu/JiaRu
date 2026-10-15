import assert from "node:assert/strict";
import test from "node:test";
import { schedule } from "../model/runtime/nail-mask-f64-v3.mjs";
import { schedule as old } from "../model/runtime/nail-mask-f64-v2.mjs";

const heapStart = 606032;
const bound = 256 * 1024 * 1024;
const overlaps = (a, b) => a.ptr < b.ptr + b.bytes && b.ptr < a.ptr + a.bytes;

test("661调度域接受且662拒绝，旧628域全部计划保持", () => {
  assert.throws(() => old(661, 661, heapStart), /controlled domain/);
  assert.throws(() => schedule(662, 661, heapStart), /controlled domain/);
  for (let n = 4; n <= 628; n++) for (const [h, w] of [[n, n], [n, 17], [17, n]]) {
    assert.deepEqual(schedule(h, w, heapStart), old(h, w, heapStart));
  }
});

test("完整661边界尺寸与奇偶对的活跃区间和256MiB约束", () => {
  for (let n = 4; n <= 661; n++) for (const [h, w] of [[n, 661], [661, n], [n, n]]) {
    const plan = schedule(h, w, heapStart);
    assert.equal(plan.steps.length, 36);
    assert.ok(plan.highWaterBytes <= bound, `${h}x${w} memory`);
    const last = new Map([[plan.input, -1], [plan.output, plan.steps.length]]);
    for (const [i, step] of plan.steps.entries()) for (const t of [step.input, step.first, step.second, step.out]) {
      if (t) last.set(t, Math.max(i, last.get(t) ?? -1));
    }
    const live = new Set([plan.input]);
    for (const [i, step] of plan.steps.entries()) {
      for (const t of live) if (last.get(t) < i) live.delete(t);
      for (const t of [step.input, step.first, step.second]) if (t) assert.ok(live.has(t));
      for (const t of live) if (t !== step.out) assert.equal(overlaps(t, step.out), false, `${h}x${w} stage ${i}`);
      assert.ok(step.out.ptr >= heapStart && step.out.ptr + step.out.bytes <= plan.highWaterBytes);
      live.add(step.out);
    }
  }
});
