import assert from "node:assert/strict";
import test from "node:test";
import { createNativeConditionalWorkerService } from "../model/runtime/native-conditional-worker-service.mjs";

const identity = { identity: { split: "train", fileName: "fixture.png", imageSha256: "a".repeat(64) }, predictionIndex: 1 };
const c = { id: "case1", candidateIdentity: identity, width: 4, height: 5 };
const request = () => ({ ...c, type: "refine", rgb: new Uint8Array(60), coarse: new Uint8Array(20),
  ratios: new Float32Array([.5, .5, .4, .5]) });
const output = () => ({ mask: new Float32Array(20).fill(-2), presence: new Float32Array([-1]), presenceExecuted: true });
async function setup(run = async () => output()) {
  const events = [], calls = [];
  const receive = createNativeConditionalWorkerService((value, transfer = []) => events.push(structuredClone(value, { transfer })),
    async () => ({ plan: () => ({ mask: { highWaterBytes: 100 }, presenceAuxiliaryArrayBytes: 10 }),
      run: async (...args) => { calls.push(args); return run(...args); } }));
  await receive({ type: "initialize", id: "init", assets: {}, cases: [c] });
  return { receive, events, calls };
}
async function prepare(s) {
  const raw = request(), transferred = structuredClone(raw, { transfer: [raw.rgb.buffer, raw.coarse.buffer, raw.ratios.buffer] });
  assert.equal(raw.rgb.byteLength, 0); assert.equal(raw.coarse.byteLength, 0); assert.equal(raw.ratios.byteLength, 0);
  await s.receive(transferred); const ready = s.events.at(-1); assert.equal(ready.type, "prepared"); return ready;
}

test("packing and transferred inputs do not execute before matching persisted-start permit", async () => {
  const s = await setup(); const ready = await prepare(s);
  assert.equal(s.calls.length, 0);
  await s.receive({ type: "execute", id: "case1", inputSha256: "wrong" }); assert.equal(s.calls.length, 0);
  await s.receive({ type: "execute", id: "case1", inputSha256: ready.inputSha256 });
  assert.equal(s.calls.length, 1); assert.equal(s.calls[0][0].length, 80);
  assert.equal(s.events.at(-1).presence[0], -1); assert.equal(s.events.at(-1).coarseFallbackUsed, false);
  assert.ok(s.events.at(-1).mask.every((x) => x === -2));
  await s.receive(request()); assert.equal(s.events.at(-1).reason, "request_already_consumed");
  assert.equal(s.calls.length, 1);
});

test("output buffers are transferred, not retained as worker aliases", async () => {
  const actual = output(), s = await setup(async () => actual), ready = await prepare(s);
  await s.receive({ type: "execute", id: "case1", inputSha256: ready.inputSha256 });
  assert.equal(actual.mask.byteLength, 0); assert.equal(actual.presence.byteLength, 0);
  assert.equal(s.events.at(-1).mask.length, 20); assert.equal(s.events.at(-1).presence.length, 1);
});

test("reentry and duplicate execute are rejected without a second model call", async () => {
  let finish; const s = await setup(() => new Promise((resolve) => { finish = resolve; })), ready = await prepare(s);
  const running = s.receive({ type: "execute", id: "case1", inputSha256: ready.inputSha256 });
  await s.receive(request()); assert.match(s.events.at(-1).reason, /busy/);
  await s.receive({ type: "execute", id: "case1", inputSha256: ready.inputSha256 });
  assert.match(s.events.at(-1).reason, /permit/); assert.equal(s.calls.length, 1);
  finish(output()); await running;
});

test("invalid identity, seed, ratios and duplicate initialization never execute", async () => {
  let s = await setup();
  await s.receive({ ...request(), candidateIdentity: { wrong: true } }); assert.match(s.events.at(-1).reason, /identity/);
  const bad = request(); bad.coarse[0] = 8; await s.receive(bad); assert.match(s.events.at(-1).reason, /binary/); assert.equal(s.calls.length, 0);
  s = await setup(); await s.receive({ ...request(), ratios: new Float32Array([1, 1, 1, 1]) }); assert.match(s.events.at(-1).reason, /ratios/);
  await s.receive({ type: "initialize", id: "init2", assets: {}, cases: [c] }); assert.match(s.events.at(-1).reason, /initialized/);
  assert.equal(s.calls.length, 0);
});

test("execution failures and nonfinite heads stay errors with no coarse fallback or retry", async () => {
  for (const run of [async () => { throw new Error("actual failure"); }, async () => ({ ...output(), presence: new Float32Array([NaN]) })]) {
    const s = await setup(run), ready = await prepare(s);
    await s.receive({ type: "execute", id: "case1", inputSha256: ready.inputSha256 });
    const e = s.events.at(-1); assert.equal(e.type, "execution-error"); assert.equal(e.consumed, true);
    assert.equal(e.coarseFallbackUsed, false); assert.equal(e.mask, undefined);
    await s.receive(request()); assert.equal(s.calls.length, 1);
  }
});

test("memory plan failure prevents worker ready and all model calls", async () => {
  const events = []; let calls = 0;
  const receive = createNativeConditionalWorkerService((x) => events.push(x), async () => ({
    plan: () => ({ mask: { highWaterBytes: 268435457 } }), run: async () => { calls++; },
  }));
  await receive({ type: "initialize", id: "init", assets: {}, cases: [c] });
  assert.equal(events.at(-1).type, "execution-error"); assert.match(events.at(-1).reason, /memory/);
  await receive(request()); assert.equal(calls, 0);
});
