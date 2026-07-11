import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("INT8 quantization candidate stays isolated and requires quality/runtime gates", async () => {
  const source = await readFile("model/training/quantize-onnx-int8.py", "utf8");

  assert.match(source, /QuantFormat\.QDQ/);
  assert.match(source, /activation_type=QuantType\.QUInt8/);
  assert.match(source, /weight_type=QuantType\.QInt8/);
  assert.match(source, /"promotionAllowed": False/);
  assert.match(source, /"browser-webgpu-and-wasm-runtime"/);
  assert.match(source, /letterbox_rgb/);
});
