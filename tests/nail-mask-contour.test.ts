import assert from "node:assert/strict";
import test from "node:test";
import { maskBoundarySegments } from "../src/lib/nail-mask-contour.ts";
import type { NailMask } from "../src/lib/nail-texture-recognition/types.ts";

function buildMask(width: number, height: number, fill: (x: number, y: number) => boolean): NailMask {
  const data = new Uint8Array(width * height);
  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      data[y * width + x] = fill(x, y) ? 1 : 0;
    }
  }
  return { width, height, data, originX: 0, originY: 0, scale: 1 };
}

test("maskBoundarySegments traces the outline of the foreground block", () => {
  const mask = buildMask(8, 8, (x, y) => x >= 2 && x < 6 && y >= 2 && y < 6);

  const segments = maskBoundarySegments(mask, { width: 8, height: 8 });

  assert.ok(segments);
  // 4×4 实心块的外周长 = 16 个像素边。
  assert.equal(segments?.length, 16);
  const ys = (segments ?? []).flatMap((segment) => [segment.y1, segment.y2]);
  assert.equal(Math.min(...ys), 2);
  assert.equal(Math.max(...ys), 6);
});

test("maskBoundarySegments ignores isolated noise pixels", () => {
  const mask = buildMask(10, 10, (x, y) => (x >= 2 && x < 6 && y >= 2 && y < 6) || (x === 9 && y === 9));

  const segments = maskBoundarySegments(mask, { width: 10, height: 10 });

  assert.ok(segments);
  assert.equal(segments?.length, 16);
});

test("maskBoundarySegments maps mask grid onto the original image size", () => {
  const mask = buildMask(6, 6, (x, y) => x >= 1 && x < 5 && y >= 1 && y < 5);

  // 掩膜按整图栅格解释：30/6 = 5，掩膜边 1..5 对应原图 5..25。
  const segments = maskBoundarySegments(mask, { width: 30, height: 30 });

  assert.ok(segments);
  const xs = (segments ?? []).flatMap((segment) => [segment.x1, segment.x2]);
  const ys = (segments ?? []).flatMap((segment) => [segment.y1, segment.y2]);
  assert.equal(Math.min(...xs), 5);
  assert.equal(Math.max(...xs), 25);
  assert.equal(Math.min(...ys), 5);
  assert.equal(Math.max(...ys), 25);
});

test("maskBoundarySegments returns null for empty or malformed masks", () => {
  assert.equal(maskBoundarySegments(null, { width: 8, height: 8 }), null);
  assert.equal(maskBoundarySegments(buildMask(6, 6, () => false), { width: 6, height: 6 }), null);
  assert.equal(
    maskBoundarySegments(
      { width: 4, height: 4, data: new Uint8Array(3), originX: 0, originY: 0, scale: 1 },
      { width: 8, height: 8 }
    ),
    null
  );
});
