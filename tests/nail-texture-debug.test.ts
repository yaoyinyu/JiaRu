import assert from "node:assert/strict";
import test from "node:test";
import {
  serializeModelOutputs,
  summarizeModelOutputs,
} from "../src/lib/nail-texture-recognition/index.ts";

test("summarizeModelOutputs reports names dims size and sample", () => {
  const summary = summarizeModelOutputs({
    output0: {
      dims: [1, 2, 3],
      data: new Float32Array([1, 2, 3, 4, 5, 6]),
    },
  });

  assert.equal(summary.length, 1);
  assert.equal(summary[0].name, "output0");
  assert.deepEqual(summary[0].dims, [1, 2, 3]);
  assert.equal(summary[0].size, 6);
  assert.deepEqual(summary[0].sample, [1, 2, 3, 4, 5, 6]);
});

test("serializeModelOutputs preserves dims and full numeric data", () => {
  const serialized = serializeModelOutputs({
    output0: {
      dims: [1, 2, 3],
      data: new Float32Array([1, 2, 3, 4, 5, 6]),
    },
  });

  assert.deepEqual(serialized, {
    output0: {
      dims: [1, 2, 3],
      data: [1, 2, 3, 4, 5, 6],
    },
  });
});
