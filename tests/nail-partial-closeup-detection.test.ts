import assert from "node:assert/strict";
import test from "node:test";

import { detectPartialCloseupNailCandidates } from "../src/lib/nail-partial-closeup-detection.ts";

function createSyntheticCloseup(nailCount: number) {
  const width = 480;
  const height = 480;
  const data = new Uint8ClampedArray(width * height * 4);
  for (let index = 0; index < width * height; index += 1) {
    data[index * 4] = 205;
    data[index * 4 + 1] = 164;
    data[index * 4 + 2] = 142;
    data[index * 4 + 3] = 255;
  }

  const nails = [
    { cx: 112, cy: 188, rx: 24, ry: 48, angle: -0.5 },
    { cx: 205, cy: 142, rx: 25, ry: 49, angle: -0.12 },
    { cx: 295, cy: 210, rx: 26, ry: 51, angle: 0.18 },
    { cx: 372, cy: 275, rx: 24, ry: 47, angle: 0.42 },
    { cx: 425, cy: 150, rx: 22, ry: 43, angle: 0.55 },
  ];
  for (const nail of nails.slice(0, nailCount)) {
    const cos = Math.cos(-nail.angle);
    const sin = Math.sin(-nail.angle);
    for (let y = nail.cy - nail.ry - 8; y <= nail.cy + nail.ry + 8; y += 1) {
      for (let x = nail.cx - nail.ry - 8; x <= nail.cx + nail.ry + 8; x += 1) {
        const dx = x - nail.cx;
        const dy = y - nail.cy;
        const localX = dx * cos - dy * sin;
        const localY = dx * sin + dy * cos;
        if (
          x >= 0 &&
          y >= 0 &&
          x < width &&
          y < height &&
          (localX * localX) / (nail.rx * nail.rx) +
            (localY * localY) / (nail.ry * nail.ry) <=
            1
        ) {
          const index = (y * width + x) * 4;
          const highlight = Math.abs(localX) < 4 && localY < 4;
          data[index] = highlight ? 105 : 24;
          data[index + 1] = highlight ? 125 : 38;
          data[index + 2] = highlight ? 150 : 70;
        }
      }
    }
  }

  // 连通的粗糙衣物区域：颜色接近候选，但没有平滑皮肤包围，必须被排除。
  for (let y = 330; y < 430; y += 1) {
    for (let x = 30; x < 440; x += 1) {
      const index = (y * width + x) * 4;
      const shade = (x + y) % 6 < 3 ? 64 : 92;
      data[index] = shade;
      data[index + 1] = shade - 3;
      data[index + 2] = shade - 7;
    }
  }
  return { width, height, data };
}

function repaintSyntheticNailSilver(
  source: ReturnType<typeof createSyntheticCloseup>,
  nail: { cx: number; cy: number; rx: number; ry: number; angle: number }
): void {
  const cos = Math.cos(-nail.angle);
  const sin = Math.sin(-nail.angle);
  for (let y = nail.cy - nail.ry - 4; y <= nail.cy + nail.ry + 4; y += 1) {
    for (let x = nail.cx - nail.ry - 4; x <= nail.cx + nail.ry + 4; x += 1) {
      const dx = x - nail.cx;
      const dy = y - nail.cy;
      const localX = dx * cos - dy * sin;
      const localY = dx * sin + dy * cos;
      if (
        x >= 0 &&
        y >= 0 &&
        x < source.width &&
        y < source.height &&
        (localX * localX) / (nail.rx * nail.rx) +
          (localY * localY) / (nail.ry * nail.ry) <=
          1
      ) {
        const index = (y * source.width + x) * 4;
        const highlight = Math.abs(localX) < 5;
        source.data[index] = highlight ? 198 : 145;
        source.data[index + 1] = highlight ? 202 : 150;
        source.data[index + 2] = highlight ? 208 : 158;
      }
    }
  }
}

test("partial closeup detector finds painted nails without exposing fabric", () => {
  const candidates = detectPartialCloseupNailCandidates(createSyntheticCloseup(4));

  assert.equal(candidates.length, 4);
  assert.ok(candidates.every((candidate) => candidate.source === "partial-closeup"));
  assert.ok(candidates.every((candidate) => candidate.confidence === "medium"));
  assert.deepEqual(
    candidates.map((candidate) => candidate.suggestedFinger),
    [0, 1, 2, 3]
  );
  assert.ok(candidates.every((candidate) => candidate.cy < 320));
});

test("partial closeup detector keeps a coherent five-nail cluster and rejects a remote decoy", () => {
  const source = createSyntheticCloseup(5);
  const decoy = { cx: 40, cy: 35, rx: 18, ry: 28 };
  for (let y = decoy.cy - decoy.ry; y <= decoy.cy + decoy.ry; y += 1) {
    for (let x = decoy.cx - decoy.rx; x <= decoy.cx + decoy.rx; x += 1) {
      if (
        x >= 0 &&
        y >= 0 &&
        x < source.width &&
        y < source.height &&
        ((x - decoy.cx) ** 2) / decoy.rx ** 2 + ((y - decoy.cy) ** 2) / decoy.ry ** 2 <= 1
      ) {
        const index = (y * source.width + x) * 4;
        source.data[index] = 20;
        source.data[index + 1] = 42;
        source.data[index + 2] = 78;
      }
    }
  }

  const candidates = detectPartialCloseupNailCandidates(source);
  assert.equal(candidates.length, 5);
  assert.ok(candidates.every((candidate) => candidate.cy > 100));
  assert.ok(candidates.every((candidate) => candidate.confidence === "medium"));
});

test("partial closeup detector keeps low-saturation silver nails", () => {
  const source = createSyntheticCloseup(5);
  repaintSyntheticNailSilver(source, {
    cx: 295,
    cy: 210,
    rx: 26,
    ry: 51,
    angle: 0.18,
  });
  repaintSyntheticNailSilver(source, {
    cx: 425,
    cy: 150,
    rx: 22,
    ry: 43,
    angle: 0.55,
  });

  const candidates = detectPartialCloseupNailCandidates(source);
  assert.equal(candidates.length, 5);
  assert.ok(candidates.every((candidate) => candidate.confidence === "medium"));
});

test("partial closeup detector refuses a lone ambiguous painted object", () => {
  assert.deepEqual(detectPartialCloseupNailCandidates(createSyntheticCloseup(1)), []);
});
