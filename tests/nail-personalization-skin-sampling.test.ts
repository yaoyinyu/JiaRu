import assert from "node:assert/strict";
import test from "node:test";

import { rgbToLab } from "../src/lib/nail-personalization/color-science.ts";
import {
  isSkinPixelRgb,
  MIN_SKIN_SAMPLES,
  MIN_SKIN_SAMPLES_SINGLE_CANDIDATE,
  samplePeriNailSkin,
} from "../src/lib/nail-personalization/skin-sampling.ts";
import type { NailTextureCandidate } from "../src/lib/nail-texture-recognition/types.ts";
import type { ImagePixels } from "../src/lib/nail-image-detection.ts";

const SKIN: [number, number, number] = [220, 180, 160];
const NAIL: [number, number, number] = [30, 40, 90];
const NOISE: [number, number, number] = [5, 5, 5];

function makeImage(
  width: number,
  height: number,
  fill: (x: number, y: number) => [number, number, number]
): ImagePixels {
  const data = new Uint8ClampedArray(width * height * 4);
  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      const [r, g, b] = fill(x, y);
      const offset = (y * width + x) * 4;
      data[offset] = r;
      data[offset + 1] = g;
      data[offset + 2] = b;
      data[offset + 3] = 255;
    }
  }
  return { width, height, data };
}

function candidate(overrides: Partial<NailTextureCandidate> = {}): NailTextureCandidate {
  return {
    id: "c1",
    cx: 200,
    cy: 200,
    length: 120,
    width: 80,
    angle: 0,
    score: 0.9,
    confidence: "high",
    source: "model",
    suggestedFinger: null,
    ...overrides,
  };
}

function insideNail(x: number, y: number): boolean {
  const dx = (x - 200) / 60;
  const dy = (y - 200) / 40;
  return dx * dx + dy * dy <= 1;
}

test("肤色判据：肤色判为皮肤、暗蓝甲面与非肤色噪点判为非皮肤", () => {
  assert.equal(isSkinPixelRgb(...SKIN), true);
  assert.equal(isSkinPixelRgb(...NAIL), false);
  assert.equal(isSkinPixelRgb(...NOISE), false);
});

test("合成环图可复现已知肤色 Lab（中位数抗噪）", () => {
  const image = makeImage(400, 400, (x, y) => {
    if (insideNail(x, y)) return NAIL;
    if ((x * 7 + y * 13) % 97 === 0) return NOISE;
    return SKIN;
  });
  const sample = samplePeriNailSkin(image, [candidate()], { expectedCandidates: 1 });
  const expected = rgbToLab(...SKIN);
  assert.ok(sample.sampleCount > 0, "采样点不应为 0");
  assert.ok(Math.abs(sample.lab.L - expected.L) < 3, `L=${sample.lab.L} vs ${expected.L}`);
  assert.ok(Math.abs(sample.lab.a - expected.a) < 3, `a=${sample.lab.a} vs ${expected.a}`);
  assert.ok(Math.abs(sample.lab.b - expected.b) < 3, `b=${sample.lab.b} vs ${expected.b}`);
});

test("甲面自污染排除：采样结果趋近肤色而非甲面颜色", () => {
  const image = makeImage(400, 400, (x, y) => (insideNail(x, y) ? NAIL : SKIN));
  const sample = samplePeriNailSkin(image, [candidate()], { expectedCandidates: 1 });
  const nailLab = rgbToLab(...NAIL);
  const skinLab = rgbToLab(...SKIN);
  assert.ok(
    Math.abs(sample.lab.L - skinLab.L) < Math.abs(sample.lab.L - nailLab.L),
    "采样结果更接近甲面色，说明甲面像素未被排除"
  );
});

test("皮肤像素全被滤除时 sampleCount=0 且出低质量警告", () => {
  const image = makeImage(400, 400, () => NAIL);
  const sample = samplePeriNailSkin(image, [candidate()], { expectedCandidates: 1 });
  assert.equal(sample.sampleCount, 0);
  assert.equal(sample.quality, 0);
  assert.ok(sample.warnings.includes("skin_sampling_low_quality"));
});

test("无候选时返回空采样并出 no_candidates 警告", () => {
  const image = makeImage(400, 400, () => SKIN);
  const sample = samplePeriNailSkin(image, [], { expectedCandidates: 1 });
  assert.equal(sample.sampleCount, 0);
  assert.ok(sample.warnings.includes("skin_sampling_no_candidates"));
});

test("采样数绝对下限生效：半幅皮肤不足以通过单候选下限", () => {
  const image = makeImage(400, 400, (x, y) => (insideNail(x, y) ? NAIL : x < 200 ? SKIN : NAIL));
  const sample = samplePeriNailSkin(image, [candidate()], { expectedCandidates: 1 });
  assert.ok(
    sample.sampleCount < MIN_SKIN_SAMPLES_SINGLE_CANDIDATE,
    `sampleCount=${sample.sampleCount} 不应达到下限 ${MIN_SKIN_SAMPLES_SINGLE_CANDIDATE}`
  );
  assert.ok(sample.warnings.includes("skin_sampling_low_quality"));
});

test("两个候选且全幅皮肤时通过多候选下限", () => {
  // 全幅皮肤：两个候选的环不互相落入对方甲面椭圆，采样点应全部有效。
  const image = makeImage(400, 400, () => SKIN);
  const candidates = [
    candidate({ id: "a", cx: 120, cy: 200 }),
    candidate({ id: "b", cx: 280, cy: 200 }),
  ];
  const sample = samplePeriNailSkin(image, candidates, { expectedCandidates: 2 });
  assert.ok(
    sample.sampleCount >= MIN_SKIN_SAMPLES,
    `sampleCount=${sample.sampleCount} 应达到 ${MIN_SKIN_SAMPLES}`
  );
  assert.equal(sample.warnings.length, 0);
});

test("quality = 皮肤像素占比 × 候选覆盖度", () => {
  const image = makeImage(400, 400, (x, y) => (insideNail(x, y) ? NAIL : SKIN));
  const full = samplePeriNailSkin(image, [candidate()], { expectedCandidates: 1 });
  const half = samplePeriNailSkin(image, [candidate()], { expectedCandidates: 2 });
  assert.ok(Math.abs(full.quality - 1) < 1e-6, `full.quality=${full.quality}`);
  assert.ok(Math.abs(half.quality - 0.5) < 1e-6, `half.quality=${half.quality}`);
});
