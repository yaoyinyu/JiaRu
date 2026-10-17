import assert from "node:assert/strict";
import test from "node:test";
import { packNativeConditionalInput } from "../model/runtime/native-conditional-input.mjs";

test("non-square native RGB keeps pixel order and produces separate normalized channels", () => {
  const rgb = new Uint8Array(4 * 5 * 3), seed = new Uint8Array(4 * 5);
  rgb.set([0, 255, 128]); rgb.set([255, 0, 64], 19 * 3); seed[19] = 255;
  const original = rgb.slice(), originalSeed = seed.slice();
  const x = packNativeConditionalInput(rgb, seed, 4, 5);
  assert.equal(x.length, 80);
  assert.deepEqual(Array.from([x[0], x[20], x[40], x[19], x[39], x[59]]),
    Array.from(new Float32Array([(0 - .485) / .229, (1 - .456) / .224, (128 / 255 - .406) / .225,
      (1 - .485) / .229, (0 - .456) / .224, (64 / 255 - .406) / .225])));
  assert.equal(x[60], 0); assert.equal(x[79], 1);
  assert.deepEqual(rgb, original); assert.deepEqual(seed, originalSeed);
});

test("maximum supported native domain is accepted without resizing", () => {
  const rgb = new Uint8Array(661 * 661 * 3), seed = new Uint8Array(661 * 661).fill(255);
  const x = packNativeConditionalInput(rgb, seed, 661, 661);
  assert.equal(x.length, 4 * 661 * 661); assert.equal(x.at(-1), 1);
});

test("invalid dimensions and storage domains reject before producing model input", () => {
  for (const bad of [0, 3, 662, 4.5, NaN, Infinity, "4"]) {
    assert.throws(() => packNativeConditionalInput(new Uint8Array(48), new Uint8Array(16), bad, 4), /controlled domain/);
  }
  assert.throws(() => packNativeConditionalInput(new Float32Array(48), new Uint8Array(16), 4, 4), /uint8/);
  assert.throws(() => packNativeConditionalInput(new Uint8Array(47), new Uint8Array(16), 4, 4), /uint8/);
  const badSeed = new Uint8Array(16); badSeed[15] = 1;
  assert.throws(() => packNativeConditionalInput(new Uint8Array(48), badSeed, 4, 4), /binary/);
});
