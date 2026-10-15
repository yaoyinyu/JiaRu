import assert from "node:assert/strict";
import test from "node:test";
import { parameterShapes, schedule } from "../model/runtime/nail-mask-f64-v2.mjs";
import { schedule as previous } from "../model/runtime/nail-mask-f64.mjs";

const start = 606032;
const intersect = (a, b) => a.ptr < b.ptr + b.bytes && b.ptr < a.ptr + a.bytes;

test("独立区间分析确认每个活跃张量均未被另一输出覆盖", () => {
  for (const h of [4, 5, 7, 31, 96, 157, 314, 628]) for (const w of [4, 9, 35, 100, 157, 314, 628]) {
    const plan = schedule(h, w, start);
    const last = new Map([[plan.input, -1], [plan.output, plan.steps.length]]);
    for (const [i, step] of plan.steps.entries()) for (const t of [step.input, step.first, step.second, step.out]) if (t) last.set(t, Math.max(i, last.get(t) ?? -1));
    const active = new Set([plan.input]);
    for (const [i, step] of plan.steps.entries()) {
      for (const t of active) if (last.get(t) < i) active.delete(t);
      for (const t of [step.input, step.first, step.second]) if (t) assert.ok(active.has(t), "read of expired tensor");
      for (const t of active) if (t !== step.out) assert.equal(intersect(t, step.out), false, `live alias ${h}x${w} stage ${i}`);
      active.add(step.out);
      assert.ok(step.out.ptr >= start && step.out.ptr + step.out.bytes <= plan.highWaterBytes);
      assert.equal(step.out.ptr % 16, 0);
    }
    assert.equal(plan.materializedConcatBytes, 0);
    assert.ok(plan.highWaterBytes <= 256 * 1024 * 1024);
  }
});

test("全36算子保持原两处跳连及floor池化形状", () => {
  const p = schedule(31, 35, start);
  assert.equal(p.steps.length, 36);
  assert.deepEqual(p.steps.filter((s) => s.op === "pool2").map((s) => [s.out.h, s.out.w]), [[15, 17], [7, 8]]);
  for (const step of p.steps.filter((s) => s.op === "conv3")) {
    assert.equal(parameterShapes[step.name][1], step.first.c + (step.second?.c ?? 0));
    assert.equal(parameterShapes[step.name][0], step.out.c);
    assert.equal(step.out.h, step.first.h);
    assert.equal(step.out.w, step.first.w);
  }
  assert.deepEqual(p.steps.filter((s) => s.second).map((s) => s.second.c), [32, 16]);
});

test("最大原尺寸在256MiB内，保留旧分配器超限事实", () => {
  assert.ok(previous(628, 628, start).highWaterBytes > 256 * 1024 * 1024);
  assert.equal(schedule(628, 628, start).highWaterBytes, 221461072);
  assert.ok(schedule(628, 628, start).peakLiveBytes < 256 * 1024 * 1024);
});

test("拒绝越域及非整数尺寸", () => {
  for (const [h, w] of [[3, 10], [10, 629], [NaN, 10], [4.5, 10], [10, Infinity]]) assert.throws(() => schedule(h, w, start));
});

test("完整参数槽包含实际delta bias且不包含presence参数", () => {
  assert.equal(Object.keys(parameterShapes).length, 32);
  assert.equal(Object.values(parameterShapes).reduce((n, s) => n + s.reduce((a, b) => a * b, 1), 0), 118737);
  assert.deepEqual(parameterShapes["delta.bias"], [1]);
  assert.ok(Object.keys(parameterShapes).every((key) => !key.startsWith("presence")));
});
