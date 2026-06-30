import assert from "node:assert/strict";
import test from "node:test";
import { findMaskBounds } from "../src/lib/nail-texture-recognition/index.ts";

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
