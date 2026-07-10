import assert from "node:assert/strict";
import test from "node:test";
import {
  calculateCoverVideoLayout,
  calculateViewportAspectRatio,
} from "../src/lib/ar-video-layout.ts";

test("same-ratio video scales to the frame without cropping", () => {
  const layout = calculateCoverVideoLayout(1920, 1080, 2560, 1440);
  assert.equal(layout.scale, 4 / 3);
  assert.equal(layout.scaledWidth, 2560);
  assert.equal(layout.scaledHeight, 1440);
  assert.equal(layout.cropX, 0);
  assert.equal(layout.cropY, 0);
});

test("landscape video is center-cropped for a portrait frame without distortion", () => {
  const layout = calculateCoverVideoLayout(1920, 1080, 1080, 1920);
  assert.equal(layout.scale, 16 / 9);
  assert.equal(layout.scaledHeight, 1920);
  assert.ok(layout.scaledWidth > 1080);
  assert.ok(layout.cropX > 0);
  assert.equal(layout.cropY, 0);
  assert.equal(layout.offsetX, -layout.cropX);
});

test("portrait video is center-cropped vertically for a landscape frame", () => {
  const layout = calculateCoverVideoLayout(1080, 1920, 1920, 1080);
  assert.equal(layout.scaledWidth, 1920);
  assert.ok(layout.scaledHeight > 1080);
  assert.equal(layout.cropX, 0);
  assert.ok(layout.cropY > 0);
});

test("viewport ratio follows the actual webpage display area", () => {
  assert.equal(calculateViewportAspectRatio(2560, 1440), 16 / 9);
  assert.equal(calculateViewportAspectRatio(1080, 1920), 9 / 16);
});

test("invalid dimensions are rejected", () => {
  assert.throws(() => calculateCoverVideoLayout(0, 1080, 1920, 1080), RangeError);
  assert.throws(() => calculateViewportAspectRatio(1080, Number.NaN), RangeError);
});
