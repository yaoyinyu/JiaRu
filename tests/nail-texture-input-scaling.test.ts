import assert from "node:assert/strict";
import test from "node:test";
import {
  calculateDetectionInputGeometry,
  remapNailTextureCandidatesToOriginal,
} from "../src/lib/nail-texture-recognition/input-scaling.ts";

test("calculateDetectionInputGeometry caps large landscape and portrait images", () => {
  assert.deepEqual(calculateDetectionInputGeometry(4000, 3000, 800), {
    width: 800,
    height: 600,
    scaleX: 0.2,
    scaleY: 0.2,
    rgbaBytes: 1_920_000,
  });
  assert.deepEqual(calculateDetectionInputGeometry(3000, 4000, 800), {
    width: 600,
    height: 800,
    scaleX: 0.2,
    scaleY: 0.2,
    rgbaBytes: 1_920_000,
  });
});

test("calculateDetectionInputGeometry keeps small images at original resolution", () => {
  assert.deepEqual(calculateDetectionInputGeometry(640, 480, 800), {
    width: 640,
    height: 480,
    scaleX: 1,
    scaleY: 1,
    rgbaBytes: 1_228_800,
  });
});

test("remapNailTextureCandidatesToOriginal restores candidate geometry and preserves mask", () => {
  const mask = {
    width: 2,
    height: 2,
    data: new Uint8Array([0, 1, 1, 0]),
    originX: 0,
    originY: 0,
    scale: 320,
  };
  const [candidate] = remapNailTextureCandidatesToOriginal(
    [
      {
        id: "nail-1",
        cx: 100,
        cy: 75,
        width: 20,
        length: 50,
        angle: 0.2,
        score: 0.9,
        confidence: "high",
        source: "model",
        mask,
        suggestedFinger: 1,
      },
    ],
    { scaleX: 0.2, scaleY: 0.25 },
    4000,
    3000
  );

  assert.equal(candidate.cx, 500);
  assert.equal(candidate.cy, 300);
  assert.equal(candidate.width, 100);
  assert.equal(candidate.length, 200);
  assert.equal(candidate.mask, mask);
});

test("calculateDetectionInputGeometry rejects invalid dimensions", () => {
  assert.throws(
    () => calculateDetectionInputGeometry(0, 100, 800),
    /invalid_detection_image_dimensions/
  );
  assert.throws(
    () => calculateDetectionInputGeometry(100, 100, 0),
    /invalid_detection_max_dimension/
  );
});
