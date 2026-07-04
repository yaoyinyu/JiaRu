import assert from "node:assert/strict";
import test from "node:test";

import {
  compareDetectedRegionsToFixture,
  findGreenAnnotationComponents,
} from "../src/lib/nail-detection-fixture.ts";

test("findGreenAnnotationComponents extracts sorted green-circle components", () => {
  const width = 20;
  const height = 10;
  const pixels = Buffer.alloc(width * height * 4, 0);

  const paint = (x: number, y: number) => {
    const offset = (y * width + x) * 4;
    pixels[offset] = 0;
    pixels[offset + 1] = 255;
    pixels[offset + 2] = 0;
    pixels[offset + 3] = 255;
  };

  for (let y = 1; y <= 2; y++) {
    for (let x = 1; x <= 2; x++) {
      paint(x, y);
    }
  }
  for (let y = 5; y <= 7; y++) {
    for (let x = 12; x <= 14; x++) {
      paint(x, y);
    }
  }

  const components = findGreenAnnotationComponents(pixels, width, height, 1);
  assert.equal(components.length, 2);
  assert.ok(components[0].cx < components[1].cx);
  assert.deepEqual(
    components.map((item) => ({ width: item.width, height: item.height, area: item.area })),
    [
      { width: 2, height: 2, area: 4 },
      { width: 3, height: 3, area: 9 },
    ]
  );
});

test("compareDetectedRegionsToFixture matches each truth region to nearest unused candidate", () => {
  const comparison = compareDetectedRegionsToFixture(
    [
      { cx: 10, cy: 10 },
      { cx: 51, cy: 50 },
      { cx: 100, cy: 100 },
    ],
    [
      { x: 0, y: 0, width: 4, height: 4, area: 16, cx: 12, cy: 11 },
      { x: 0, y: 0, width: 4, height: 4, area: 16, cx: 50, cy: 48 },
    ]
  );

  assert.equal(comparison.matchedTruthCount, 2);
  assert.equal(comparison.matches.length, 2);
  assert.equal(comparison.matches[0]?.predictedIndex, 0);
  assert.equal(comparison.matches[1]?.predictedIndex, 1);
  assert.ok(comparison.maxCenterError > 0);
});
