import assert from "node:assert/strict";
import test from "node:test";
import {
  buildFeatheredAlphaMask,
  findMaskBounds,
  isSpecularHighlightPixel,
  inspectSpecularHighlights,
  repairSpecularHighlights,
  summarizeMaskExtractionQuality,
} from "../src/lib/nail-texture-recognition/index.ts";

test("findMaskBounds returns tight bounds around foreground pixels", () => {
  const bounds = findMaskBounds({
    width: 4,
    height: 3,
    data: new Uint8Array([
      0, 0, 0, 0,
      0, 1, 1, 0,
      0, 1, 0, 0,
    ]),
    originX: 0,
    originY: 0,
    scale: 1,
  });

  assert.deepEqual(bounds, {
    minX: 1,
    minY: 1,
    maxX: 2,
    maxY: 2,
  });
});

test("buildFeatheredAlphaMask softens edge pixels while keeping inner pixels opaque", () => {
  const alpha = buildFeatheredAlphaMask(
    {
      width: 5,
      height: 5,
      data: new Uint8Array([
        0, 0, 0, 0, 0,
        0, 1, 1, 1, 0,
        0, 1, 1, 1, 0,
        0, 1, 1, 1, 0,
        0, 0, 0, 0, 0,
      ]),
      originX: 0,
      originY: 0,
      scale: 1,
    },
    2
  );

  assert.equal(alpha[2 * 5 + 2], 255);
  assert.ok(alpha[1 * 5 + 1] < 255);
  assert.equal(alpha[0], 0);
});

test("summarizeMaskExtractionQuality reports sparse and edge-touching crops", () => {
  const summary = summarizeMaskExtractionQuality({
    width: 4,
    height: 4,
    data: new Uint8Array([
      1, 0, 0, 0,
      0, 1, 0, 0,
      0, 0, 1, 0,
      0, 0, 0, 0,
    ]),
    originX: 0,
    originY: 0,
    scale: 1,
  });

  assert.equal(summary.ok, false);
  assert.ok(summary.warnings.includes("dirty_mask_crop"));
  assert.ok(summary.warnings.includes("mask_crop_touches_edge"));
  assert.ok(summary.warnings.includes("mask_foreground_too_small"));
});

test("isSpecularHighlightPixel identifies bright low-saturation glare", () => {
  assert.equal(isSpecularHighlightPixel(255, 250, 248, 255), true);
  assert.equal(isSpecularHighlightPixel(255, 180, 120, 255), false);
  assert.equal(isSpecularHighlightPixel(255, 255, 255, 0), false);
});

test("repairSpecularHighlights blends glare pixels from nearby texture colors", () => {
  const imageData = {
    width: 3,
    height: 3,
    data: new Uint8ClampedArray([
      180, 40, 60, 255, 180, 40, 60, 255, 180, 40, 60, 255,
      180, 40, 60, 255, 255, 255, 252, 255, 180, 40, 60, 255,
      180, 40, 60, 255, 180, 40, 60, 255, 180, 40, 60, 255,
    ]),
  } as ImageData;

  const summary = repairSpecularHighlights(imageData, 2);
  const center = 4 * 4;

  assert.equal(summary.highlightPixels, 1);
  assert.equal(summary.strategy, "repair");
  assert.equal(summary.repairedPixels, 1);
  assert.ok(summary.highlightRatio > 0.1);
  assert.ok(imageData.data[center] < 255);
  assert.ok(imageData.data[center + 1] < 255);
  assert.ok(imageData.data[center + 2] < 255);
  assert.ok(imageData.data[center] > 180);
});

test("inspectSpecularHighlights reports glare without changing source pixels", () => {
  const data = new Uint8ClampedArray([
    180, 40, 60, 255,
    255, 255, 252, 255,
  ]);
  const imageData = { width: 2, height: 1, data } as ImageData;
  const before = new Uint8ClampedArray(data);

  const summary = inspectSpecularHighlights(imageData);

  assert.equal(summary.strategy, "preserve");
  assert.equal(summary.highlightPixels, 1);
  assert.equal(summary.repairedPixels, 0);
  assert.equal(summary.highlightRatio, 0.5);
  assert.deepEqual(data, before);
});
