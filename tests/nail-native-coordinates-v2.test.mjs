import assert from "node:assert/strict";
import test from "node:test";
import { nativeCoordinateArrays as previous } from "../model/runtime/nail-native-coordinates.mjs";
import { nativeCoordinateArrays, nativeAxisCoordinates } from "../model/runtime/nail-native-coordinates-v2.mjs";

const ratios = (n) => new Float32Array([(n >> 2) / (n >> 1), (n >> 2) / (n >> 1), (n >> 1) / n, (n >> 1) / n]);
test("661域端点接受、662拒绝且旧628失败保持", () => {
  const result = nativeCoordinateArrays(661, 661, ratios(661));
  assert.equal(result.nativeCoord_dec1_x_lower.values.length, 661);
  assert.equal(result.nativeCoord_dec1_x_upper.values.at(-1), 329);
  assert.throws(() => nativeCoordinateArrays(662, 661, ratios(661)), /controlled native size/);
  assert.throws(() => previous(661, 661, ratios(661)), /controlled native size/);
  assert.throws(() => nativeAxisCoordinates(330, 661, .5), /native axis domain/);
});
test("完整旧4至628域的所有字段与存储域不变", () => {
  for (let n = 4; n <= 628; n++) {
    const old = previous(n, n, ratios(n)), fresh = nativeCoordinateArrays(n, n, ratios(n));
    assert.deepEqual(Object.keys(fresh), Object.keys(old));
    for (const key of Object.keys(old)) assert.deepEqual(fresh[key], old[key]);
  }
});
