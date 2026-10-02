import assert from "node:assert/strict";
import test from "node:test";
import { nativeBoundaryBand, packNativeBoundaryInput, composeNativeBoundaryProbability, decodeNativeBoundaryDelta } from "../src/lib/nail-texture-recognition/native-boundary-refinement.ts";

test("原尺寸窄带不缩放输入，保留原图归属和带外概率位", () => {
  const width = 23, height = 19, pixels = width * height, base = new Float32Array(pixels).fill(0.03);
  for (let y = 5; y < 15; y++) for (let x = 7; x < 18; x++) base[y * width + x] = 0.9;
  const rgb = new Uint8Array(pixels * 3).fill(127), coarse = new Uint8Array(pixels);
  const input = packNativeBoundaryInput(rgb, coarse, base, width, height);
  assert.equal(input.packed.length, pixels * 6);
  assert.equal(input.packed[0], Math.fround((127 / 255 - 0.485) / 0.229));
  const result = composeNativeBoundaryProbability(base, new Float32Array(pixels).fill(20), width, height);
  const before = new Uint32Array(base.buffer), after = new Uint32Array(result.buffer);
  for (let i = 0; i < pixels; i++) if (!input.band[i]) assert.equal(after[i], before[i]);
  const decoded = decodeNativeBoundaryDelta(base, new Float32Array(pixels), [1, 1, height, width], [3, 4, 26, 23], [30, 28]);
  assert.equal(decoded.kind, "mask");
  if (decoded.kind === "mask") { assert.equal(decoded.width, width); assert.deepEqual(decoded.cropBox, [3, 4, 26, 23]); }
});

test("ROI边界零填充及4原像素编辑半径固定", () => {
  const base = new Float32Array(121); base[0] = 1;
  const band = nativeBoundaryBand(base, 11, 11);
  assert.equal(band[4 * 11 + 4], 1); assert.equal(band[5 * 11 + 5], 0);
  assert.equal(Array.from(band).reduce((a, b) => a + b, 0), 25);
});

test("空基底拒识，非法残差和输入错误不作成功回退", () => {
  const base = new Float32Array(24).fill(0.01), delta = new Float32Array(24).fill(80);
  assert.deepEqual(composeNativeBoundaryProbability(base, delta, 6, 4), base);
  assert.equal(decodeNativeBoundaryDelta(base, delta, [1, 1, 4, 6], [0, 0, 6, 4], [6, 4]).kind, "rejected");
  delta[0] = NaN;
  assert.equal(decodeNativeBoundaryDelta(base, delta, [1, 1, 4, 6], [0, 0, 6, 4], [6, 4]).kind, "execution-error");
  assert.equal(decodeNativeBoundaryDelta(base, new Float32Array(24), [1, 1, 6, 4], [0, 0, 6, 4], [6, 4]).kind, "execution-error");
  assert.throws(() => packNativeBoundaryInput(new Uint8Array(72), new Uint8Array(24).fill(1), base, 6, 4));
});
