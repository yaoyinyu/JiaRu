import assert from "node:assert/strict";
import test from "node:test";
import {
  calculateCoverVideoLayout,
  calculateViewportAspectRatio,
  coverPointToVideo,
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
  assert.equal(layout.cropLeft, layout.cropRight);
  assert.equal(layout.cropTop, 0);
  assert.equal(layout.cropBottom, 0);
  assert.equal(layout.offsetX, -layout.cropX);
});

test("portrait video is center-cropped vertically for a landscape frame", () => {
  const layout = calculateCoverVideoLayout(1080, 1920, 1920, 1080);
  assert.equal(layout.scaledWidth, 1920);
  assert.ok(layout.scaledHeight > 1080);
  assert.equal(layout.cropX, 0);
  assert.ok(layout.cropY > 0);
  assert.equal(layout.cropLeft, 0);
  assert.equal(layout.cropRight, 0);
  assert.equal(layout.cropTop, layout.cropBottom);
});

test("viewport ratio follows the actual webpage display area", () => {
  assert.equal(calculateViewportAspectRatio(2560, 1440), 16 / 9);
  assert.equal(calculateViewportAspectRatio(1080, 1920), 9 / 16);
});

test("invalid dimensions are rejected", () => {
  assert.throws(() => calculateCoverVideoLayout(0, 1080, 1920, 1080), RangeError);
  assert.throws(() => calculateViewportAspectRatio(1080, Number.NaN), RangeError);
});

test("light samples return to the matching source pixel after cover crop and scaling", () => {
  for (const [sw, sh, fw, fh] of [[1920,1080,390,800], [720,1280,1280,720], [640,480,800,600]]) {
    const layout = calculateCoverVideoLayout(sw, sh, fw, fh);
    for (const [x,y] of [[fw/2,fh/2], [0,0], [fw,fh]]) {
      const source = coverPointToVideo(x, y, sw, sh, fw, fh);
      assert.ok(Math.abs(source.x * layout.scale + layout.offsetX - x) < 1e-8);
      assert.ok(Math.abs(source.y * layout.scale + layout.offsetY - y) < 1e-8);
    }
  }
});
