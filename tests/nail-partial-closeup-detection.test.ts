import assert from "node:assert/strict";
import test from "node:test";

import {
  assignPartialCloseupCandidateFingers,
  detectPartialCloseupNailCandidates,
  detectPartialCloseupNails,
} from "../src/lib/nail-partial-closeup-detection.ts";
import type { NailTextureCandidate } from "../src/lib/nail-texture-recognition/types.ts";

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

function roughenSkinAroundNail(
  source: ReturnType<typeof createSyntheticCloseup>,
  nail: { cx: number; cy: number; rx: number; ry: number; angle: number }
): void {
  const cos = Math.cos(-nail.angle);
  const sin = Math.sin(-nail.angle);
  for (let y = nail.cy - nail.ry - 18; y <= nail.cy + nail.ry + 18; y += 1) {
    for (let x = nail.cx - nail.ry - 18; x <= nail.cx + nail.ry + 18; x += 1) {
      if (x < 0 || y < 0 || x >= source.width || y >= source.height) continue;
      const dx = x - nail.cx;
      const dy = y - nail.cy;
      const localX = dx * cos - dy * sin;
      const localY = dx * sin + dy * cos;
      const normalized =
        (localX * localX) / (nail.rx * nail.rx) +
        (localY * localY) / (nail.ry * nail.ry);
      if (normalized <= 1 || normalized > 1.65) continue;
      const index = (y * source.width + x) * 4;
      const bright = (x + y) % 2 === 0;
      source.data[index] = bright ? 226 : 184;
      source.data[index + 1] = bright ? 177 : 142;
      source.data[index + 2] = bright ? 147 : 121;
    }
  }
}

function createArcCandidates(mirrored = false, ambiguous = false): NailTextureCandidate[] {
  const points = [
    { x: 110, y: 285, width: ambiguous ? 28 : 46 },
    { x: 165, y: 185, width: 28 },
    { x: 240, y: 145, width: 29 },
    { x: 315, y: 180, width: 27 },
    { x: 370, y: 280, width: ambiguous ? 28 : 22 },
  ];
  return points.map((point, index) => ({
    id: `arc-${index}`,
    cx: mirrored ? 480 - point.x : point.x,
    cy: point.y,
    length: 70,
    width: point.width,
    angle: 0,
    score: 1,
    confidence: "medium",
    source: "partial-closeup",
    suggestedFinger: null,
  }));
}

function createLowContrastNudeCloseup(nailCount: number) {
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
    { cx: 102, cy: 112, rx: 21, ry: 37, angle: -0.65 },
    { cx: 170, cy: 155, rx: 22, ry: 39, angle: -0.35 },
    { cx: 234, cy: 213, rx: 23, ry: 41, angle: -0.08 },
    { cx: 294, cy: 275, rx: 22, ry: 38, angle: 0.28 },
    { cx: 350, cy: 338, rx: 20, ry: 34, angle: 0.58 },
  ];

  for (const nail of nails.slice(0, nailCount)) {
    const cos = Math.cos(-nail.angle);
    const sin = Math.sin(-nail.angle);
    for (let y = nail.cy - nail.ry - 4; y <= nail.cy + nail.ry + 4; y += 1) {
      for (let x = nail.cx - nail.ry - 4; x <= nail.cx + nail.ry + 4; x += 1) {
        if (x < 0 || y < 0 || x >= width || y >= height) continue;
        const dx = x - nail.cx;
        const dy = y - nail.cy;
        const localX = dx * cos - dy * sin;
        const localY = dx * sin + dy * cos;
        const normalized =
          (localX * localX) / (nail.rx * nail.rx) +
          (localY * localY) / (nail.ry * nail.ry);
        if (normalized > 1.12) continue;
        const offset = (y * width + x) * 4;
        const boundary = normalized >= 0.92;
        const highlight = !boundary && Math.abs(localX + nail.rx * 0.25) < 2;
        data[offset] = boundary ? 171 : highlight ? 212 : 188;
        data[offset + 1] = boundary ? 127 : highlight ? 190 : 155;
        data[offset + 2] = boundary ? 118 : highlight ? 184 : 148;
      }
    }
  }

  return { width, height, data };
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
  assert.ok(candidates.every((candidate) => candidate.confidence !== "high"));
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
  assert.ok(candidates.every((candidate) => candidate.confidence !== "high"));
});

test("partial closeup detector keeps five nails surrounded by dry textured skin", () => {
  const source = createSyntheticCloseup(5);
  roughenSkinAroundNail(source, {
    cx: 205,
    cy: 142,
    rx: 25,
    ry: 49,
    angle: -0.12,
  });
  roughenSkinAroundNail(source, {
    cx: 372,
    cy: 275,
    rx: 24,
    ry: 47,
    angle: 0.42,
  });

  const result = detectPartialCloseupNails(source);
  assert.equal(result.candidates.length, 5, JSON.stringify(result.diagnostics));
  assert.ok(result.candidates.every((candidate) => candidate.suggestedFinger === null));
  assert.ok(
    result.candidates.every((candidate) =>
      candidate.warnings?.includes("partial_closeup_finger_order_ambiguous")
    )
  );
  assert.equal(result.diagnostics.selectedCandidateCount, 5);
  assert.ok(result.diagnostics.componentCount > result.diagnostics.acceptedComponentCount);
  assert.ok((result.diagnostics.rejectionCounts.area_too_large ?? 0) >= 1);
});

test("partial closeup detector refuses a lone ambiguous painted object", () => {
  assert.deepEqual(detectPartialCloseupNailCandidates(createSyntheticCloseup(1)), []);
});

test("partial closeup detector finds a coherent chain of skin-toned nude nails", () => {
  const result = detectPartialCloseupNails(createLowContrastNudeCloseup(5));

  assert.equal(result.candidates.length, 5);
  assert.ok(
    result.candidates.every((candidate) =>
      candidate.warnings?.includes("partial_closeup_low_contrast_boundary")
    )
  );
  assert.equal(result.diagnostics.strategy, "low-contrast-boundary");
  assert.equal(result.diagnostics.lowContrastSelectedCandidateCount, 5);
});

test("partial closeup detector hides fewer than four skin-toned boundary regions", () => {
  const result = detectPartialCloseupNails(createLowContrastNudeCloseup(3));

  assert.deepEqual(result.candidates, []);
  assert.notEqual(result.diagnostics.strategy, "low-contrast-boundary");
  assert.equal(result.diagnostics.lowContrastSelectedCandidateCount, 0);
});

test("hand arc assignment keeps the thumb first for normal and mirrored hands", () => {
  const normal = assignPartialCloseupCandidateFingers(createArcCandidates(), 240, 350);
  const mirrored = assignPartialCloseupCandidateFingers(createArcCandidates(true), 240, 350);

  assert.deepEqual(normal.map((candidate) => candidate.suggestedFinger), [0, 1, 2, 3, 4]);
  assert.deepEqual(mirrored.map((candidate) => candidate.suggestedFinger), [0, 1, 2, 3, 4]);
  assert.ok(normal[0].cx < normal[4].cx);
  assert.ok(mirrored[0].cx > mirrored[4].cx);
});

test("hand arc assignment leaves symmetric endpoints unassigned", () => {
  const assigned = assignPartialCloseupCandidateFingers(
    createArcCandidates(false, true),
    240,
    350
  );

  assert.ok(assigned.every((candidate) => candidate.suggestedFinger === null));
  assert.ok(
    assigned.every((candidate) =>
      candidate.warnings?.includes("partial_closeup_finger_order_ambiguous")
    )
  );
});
