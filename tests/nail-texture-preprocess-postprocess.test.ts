import assert from "node:assert/strict";
import test from "node:test";
import {
  estimateMaskPrincipalAngle,
  postprocessNailTextureDetections,
  preprocessNailTextureImage,
} from "../src/lib/nail-texture-recognition/index.ts";

test("preprocessNailTextureImage creates CHW float tensor", () => {
  const source = {
    width: 2,
    height: 1,
    data: new Uint8ClampedArray([
      255, 0, 0, 255,
      0, 128, 255, 255,
    ]),
  };
  const result = preprocessNailTextureImage(source, 2);
  assert.deepEqual(result.tensorShape, [1, 3, 2, 2]);
  assert.equal(result.tensorData[0], 1);
  assert.equal(result.tensorData[4], 0);
  assert.ok(result.tensorData[8] >= 0 && result.tensorData[8] <= 1);
});

test("postprocessNailTextureDetections maps model rows to candidates", () => {
  const preprocess = {
    inputSize: 640,
    originalWidth: 860,
    originalHeight: 645,
    scaleX: 860 / 640,
    scaleY: 645 / 640,
    tensorData: new Float32Array(),
    tensorShape: [1, 3, 640, 640] as [1, 3, number, number],
  };

  const candidates = postprocessNailTextureDetections(
    {
      output0: {
        dims: [1, 2, 6],
        data: new Float32Array([
          100, 120, 60, 100, 0.9, 0,
          260, 140, 55, 95, 0.6, 0,
        ]),
      },
    },
    preprocess
  );

  assert.equal(candidates.length, 2);
  assert.equal(candidates[0].source, "model");
  assert.equal(candidates[0].suggestedFinger, 1);
  assert.ok(candidates[0].cx < candidates[1].cx);
  assert.equal(candidates[0].confidence, "high");
  assert.equal(candidates[1].confidence, "medium");
});

test("estimateMaskPrincipalAngle and postprocess keep a stable mask-derived angle", () => {
  const angle = estimateMaskPrincipalAngle({
    width: 5,
    height: 5,
    data: new Uint8Array([
      0, 0, 0, 0, 0,
      0, 1, 1, 1, 0,
      0, 1, 1, 1, 0,
      0, 0, 0, 0, 0,
      0, 0, 0, 0, 0,
    ]),
    originX: 0,
    originY: 0,
    scale: 1,
  });

  assert.ok(typeof angle === "number");
  assert.ok(Math.abs(Math.abs(angle ?? 0) - Math.PI / 2) < 0.15);

  const preprocess = {
    inputSize: 640,
    originalWidth: 640,
    originalHeight: 640,
    scaleX: 1,
    scaleY: 1,
    tensorData: new Float32Array(),
    tensorShape: [1, 3, 640, 640] as [1, 3, number, number],
  };

  const candidates = postprocessNailTextureDetections(
    {
      output0: {
        dims: [1, 1, 6],
        data: new Float32Array([320, 320, 120, 60, 0.95, 1]),
      },
      output1: {
        dims: [1, 1, 4, 4],
        data: new Float32Array([
          -8, -8, -8, -8,
          8, 8, 8, 8,
          -8, -8, -8, -8,
          -8, -8, -8, -8,
        ]),
      },
    },
    preprocess
  );

  assert.equal(candidates.length, 1);
  assert.ok(Math.abs(Math.abs(candidates[0].angle) - Math.PI / 2) < 0.2);
});
