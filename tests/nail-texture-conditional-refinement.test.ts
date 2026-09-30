import assert from "node:assert/strict";
import test from "node:test";
import { decodeConditionalRefinement, packConditionalRefinementInput } from "../src/lib/nail-texture-recognition/conditional-refinement.ts";

test("条件输入保持RGB归一化且粗mask为独立0/1通道", () => {
  const pixels = 384 ** 2;
  const rgb = new Uint8Array(pixels * 3).fill(128);
  const coarse = new Uint8Array(pixels); coarse[12] = 255;
  const value = packConditionalRefinementInput(rgb, coarse);
  assert.equal(value.length, pixels * 4);
  assert.ok(Math.abs(value[0] - (128 / 255 - 0.485) / 0.229) < 1e-6);
  assert.equal(value[pixels * 3 + 12], 1);
  assert.equal(value[pixels * 3 + 13], 0);
  coarse[13] = 127;
  assert.throws(() => packConditionalRefinementInput(rgb, coarse));
});

test("有效空输出拒识，非有限或越界属于执行错误", () => {
  const logits = new Float32Array(384 ** 2).fill(-16);
  const decode = () => decodeConditionalRefinement(logits, [1, 1, 384, 384], [3, 5, 103, 205], [400, 500]);
  assert.equal(decode().kind, "rejected");
  logits[0] = NaN;
  assert.equal(decode().kind, "execution-error");
  assert.equal(decodeConditionalRefinement(logits, [1, 1, 384, 384], [-1, 0, 400, 400], [400, 400]).kind, "execution-error");
});

test("贴边目标映回原图裁块，保持尺寸与归属且不把邻甲粗mask作为回退", () => {
  const logits = new Float32Array(384 ** 2).fill(-16);
  for (let y = 0; y < 384; y++) for (let x = 0; x < 192; x++) logits[y * 384 + x] = 16;
  const result = decodeConditionalRefinement(logits, [1, 1, 384, 384], [0, 20, 96, 116], [100, 200]);
  assert.equal(result.kind, "mask");
  if (result.kind !== "mask") return;
  assert.equal(result.width, 96); assert.equal(result.height, 96);
  assert.deepEqual(result.cropBox, [0, 20, 96, 116]);
  assert.equal(result.mask[0], 1); assert.equal(result.mask[95], 0);
  assert.equal(result.mask.reduce((sum, v) => sum + v, 0), 96 * 48);
});

test("上采样边界恰在0.5时按float32概率判定，与Python浮点逆映射一致", () => {
  const logits = new Float32Array(384 ** 2).fill(-16);
  logits.fill(16, 0, 138 * 384);
  const result = decodeConditionalRefinement(logits, [1, 1, 384, 384], [0, 0, 544, 544], [544, 544]);
  assert.equal(result.kind, "mask");
  if (result.kind !== "mask") return;
  assert.equal(result.mask[195 * 544 + 270], 1);
  assert.equal(result.mask[196 * 544 + 270], 0);
});
