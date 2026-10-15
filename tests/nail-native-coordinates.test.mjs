import assert from "node:assert/strict";
import test from "node:test";
import { coordinateInputNames, nativeCoordinateArrays, nativeCoordinateFeeds, nativeAxisCoordinates } from "../model/runtime/nail-native-coordinates.mjs";
import { createTwoHeadRoute } from "../model/runtime/nail-two-head-native-coordinates.mjs";

test("原生坐标端点、存储域及两级奇数尺寸完整覆盖", () => {
  const h = 591, ratios = new Float32Array([147 / 295, 147 / 295, 295 / 591, 295 / 591]);
  const rows = nativeCoordinateArrays(h, h, ratios);
  assert.deepEqual(Object.keys(rows), coordinateInputNames);
  assert.equal(rows.nativeCoord_dec2_y_lower.values.length, 295);
  assert.equal(rows.nativeCoord_dec1_x_weight1.values.length, 591);
  assert.deepEqual(rows.nativeCoord_dec1_x_weight1.dims, [1, 1, 1, 591]);
  assert.throws(() => nativeCoordinateArrays(3, 591, ratios), /controlled native size/);
  const bad = ratios.slice(); bad[0] = .5;
  assert.throws(() => nativeCoordinateArrays(h, h, bad), /native axis domain/);
});

test("边缘钳制与F32坐标精度保持，整数输入使用真正int64", () => {
  const values = nativeAxisCoordinates(2, 4, .5);
  assert.deepEqual(Array.from(values.lower), [0, 0, 0, 1]);
  assert.deepEqual(Array.from(values.upper), [1, 1, 1, 1]);
  assert.deepEqual(Array.from(values.weight1), [0, .25, .75, .25]);
  class Tensor { constructor(type, data, dims) { Object.assign(this, { type, data, dims }); } }
  const feed = nativeCoordinateFeeds({ Tensor }, 4, 4, new Float32Array([.5, .5, .5, .5]));
  assert.equal(feed.nativeCoord_dec2_y_lower.type, "int64");
  assert.equal(feed.nativeCoord_dec2_y_lower.data instanceof BigInt64Array, true);
  assert.equal(feed.nativeCoord_dec2_y_weight1.type, "float32");
});

test("新路由使用完整18输入并读取本次presence，开始回调先于推理", async () => {
  let started = false, calls = 0;
  const output = (dims, data) => ({ type: "float32", dims, getData: async () => data });
  const session = { inputNames: ["candidate", "resizeRatios", ...coordinateInputNames], outputNames: ["mask_logits", "presence_logit"],
    run: async (feed) => {
      assert.equal(started, true); calls++;
      assert.equal(Object.keys(feed).length, 18);
      assert.equal(feed.nativeCoord_dec1_y_lower.data instanceof BigInt64Array, true);
      return { mask_logits: output([1, 1, 4, 4], new Float32Array(16).fill(-2)), presence_logit: output([1, 1], new Float32Array([-.5])) };
    }, release: async () => {} };
  const ort = { Tensor: class { constructor(type, data, dims) { Object.assign(this, { type, data, dims }); } },
    InferenceSession: { create: async () => session } };
  const route = await createTwoHeadRoute(ort, new ArrayBuffer(0), null, "webgpu");
  const result = await route.run(new Float32Array(64), 4, 4, new Float32Array([.5, .5, .5, .5]),
    async () => { started = true; }, async () => { throw Error("unexpected mask route"); });
  assert.equal(result.presence[0], -.5); assert.equal(result.maskRoute, "f32_webgpu_native_coordinates");
  assert.equal(calls, 1); await route.release();
});
