import assert from "node:assert/strict";
import test from "node:test";
import { createTwoHeadRoute } from "../model/runtime/nail-two-head-route.mjs";

function fixture(presence = 2) {
  let calls = 0, releases = 0;
  const original = new Float32Array([presence]);
  const output = (dims, data) => ({ type: "float32", dims, getData: async () => data });
  const session = { inputNames: ["candidate", "resizeRatios"], outputNames: ["mask_logits", "presence_logit"],
    run: async () => { calls++; return { mask_logits: output([1, 1, 4, 4], new Float32Array(16).fill(1)), presence_logit: output([1, 1], original) }; },
    release: async () => { releases++; } };
  const ort = { Tensor: class { constructor(type, data, dims) { Object.assign(this, { type, data, dims }); } },
    InferenceSession: { create: async (_, options) => { assert.deepEqual(options.executionProviders, ["webgpu"]); return session; } } };
  return { ort, session, original, calls: () => calls, releases: () => releases };
}
const candidate = () => new Float32Array(64), ratios = () => new Float32Array([.5, .5, .5, .5]);

test("presence从本次实际session读取并复制，回调先于session.run", async () => {
  const f = fixture(-.25), route = await createTwoHeadRoute(f.ort, new ArrayBuffer(0), null, "webgpu");
  let start = false;
  const run = f.session.run;
  f.session.run = async () => { assert.equal(start, true); return run(); };
  const result = await route.run(candidate(), 4, 4, ratios(), async () => { start = true; }, () => { throw Error("WebGPU不应执行WASM mask"); });
  f.original[0] = 9;
  assert.equal(result.presence[0], -.25); assert.equal(result.actualPresenceExecuted, true);
  assert.equal(result.maskRoute, "original_f32_webgpu"); assert.equal(result.unusedOriginalWasmMask, null);
  assert.equal(f.calls(), 1); await route.release(); assert.equal(f.releases(), 1);
});

test("小presence头NaN拒绝，不能被有限mask掩盖", async () => {
  const f = fixture(NaN), route = await createTwoHeadRoute(f.ort, new ArrayBuffer(0), null, "webgpu");
  await assert.rejects(route.run(candidate(), 4, 4, ratios(), async () => {}, async () => {}), /both actual original heads finite/);
  assert.equal(f.calls(), 1); await route.release();
});

test("开始事件等待时并发请求被拒绝，不能额外消费一次session", async () => {
  const f = fixture(), route = await createTwoHeadRoute(f.ort, new ArrayBuffer(0), null, "webgpu");
  let release;
  const barrier = new Promise((resolve) => { release = resolve; });
  const pending = route.run(candidate(), 4, 4, ratios(), () => barrier, async () => {});
  await assert.rejects(route.run(candidate(), 4, 4, ratios(), async () => {}, async () => {}), /concurrent two-head route rejected/);
  assert.equal(f.calls(), 0); release(); await pending; assert.equal(f.calls(), 1); await route.release();
});

test("坏输入先于开始事件和实际session拒绝", async () => {
  const f = fixture(), route = await createTwoHeadRoute(f.ort, new ArrayBuffer(0), null, "webgpu");
  const bad = candidate(); bad[0] = Infinity;
  await assert.rejects(route.run(bad, 4, 4, ratios(), () => { throw Error("不可到达"); }, async () => {}), /original finite inputs/);
  assert.equal(f.calls(), 0); await route.release();
});
