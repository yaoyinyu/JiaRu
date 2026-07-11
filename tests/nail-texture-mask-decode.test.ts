import assert from "node:assert/strict";
import test from "node:test";
import { postprocessNailTextureDetections } from "../src/lib/nail-texture-recognition/index.ts";

test("postprocessNailTextureDetections decodes prototype masks when coefficients exist", () => {
  const preprocess = {
    inputSize: 4,
    originalWidth: 80,
    originalHeight: 80,
    scaleX: 20,
    scaleY: 20,
    tensorData: new Float32Array(),
    tensorShape: [1, 3, 4, 4] as [1, 3, number, number],
  };

  const candidates = postprocessNailTextureDetections(
    {
      boxes: {
        dims: [1, 1, 6],
        data: new Float32Array([2, 2, 0.5, 0.5, 0.9, 5]),
      },
      proto: {
        dims: [1, 1, 2, 2],
        data: new Float32Array([
          1, -1,
          1, -1,
        ]),
      },
    },
    preprocess
  );

  assert.equal(candidates.length, 1);
  assert.ok(candidates[0].mask);
  assert.equal(candidates[0].mask?.width, 2);
  assert.equal(candidates[0].mask?.height, 2);
  assert.deepEqual(Array.from(candidates[0].mask?.data ?? []), [1, 0, 1, 0]);
});

test("postprocessNailTextureDetections crops decoded masks to the candidate box", () => {
  const preprocess = {
    inputSize: 8,
    originalWidth: 80,
    originalHeight: 80,
    scaleX: 10,
    scaleY: 10,
    tensorData: new Float32Array(),
    tensorShape: [1, 3, 8, 8] as [1, 3, number, number],
  };

  const [candidate] = postprocessNailTextureDetections(
    {
      boxes: {
        dims: [1, 1, 6],
        data: new Float32Array([4, 4, 1.6, 2.4, 0.9, 5]),
      },
      proto: {
        dims: [1, 1, 4, 4],
        data: new Float32Array(16).fill(1),
      },
    },
    preprocess
  );

  const foreground = Array.from(candidate.mask?.data ?? []).reduce(
    (sum, value) => sum + value,
    0
  );
  assert.equal(candidate.mask?.width, 4);
  assert.equal(candidate.mask?.height, 4);
  assert.equal(foreground, 4);
});
