import assert from "node:assert/strict";
import { test } from "node:test";
import { getCoherentPalmTranslation } from "../src/lib/ar-palm-translation.ts";

const palm = Array.from({ length: 21 }, (_, index) => {
  const anchors: Record<number, [number, number]> = {
    0: [0, 55], 5: [-40, 5], 9: [-12, 0], 13: [14, 2], 17: [40, 10],
  };
  const [x, y] = anchors[index] ?? [0, 0];
  return { x, y };
});

test("uses the shared palm displacement despite one unstable landmark", () => {
  const moved = palm.map(({ x, y }, index) => ({ x: x - 12, y: y + (index === 0 ? 18 : 3) }));
  assert.deepEqual(getCoherentPalmTranslation(palm, moved), { x: -12, y: 3 });
});

test("leaves tiny jitter, discontinuities, and rotation to the existing filter", () => {
  assert.equal(getCoherentPalmTranslation(palm, palm.map(p => ({ x: p.x + 1, y: p.y }))), undefined);
  assert.equal(getCoherentPalmTranslation(palm, palm.map(p => ({ x: p.x + 70, y: p.y }))), undefined);
  const angle = Math.PI / 8;
  const rotated = palm.map(({ x, y }) => ({
    x: 12 + x * Math.cos(angle) - y * Math.sin(angle),
    y: 3 + x * Math.sin(angle) + y * Math.cos(angle),
  }));
  assert.equal(getCoherentPalmTranslation(palm, rotated), undefined);
});
