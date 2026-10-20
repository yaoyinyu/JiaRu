import assert from "node:assert/strict";
import test from "node:test";

import { samplePeriNailSkin } from "../src/lib/nail-personalization/skin-sampling.ts";
import type { NailTextureCandidate } from "../src/lib/nail-texture-recognition/types.ts";
import type { ImagePixels } from "../src/lib/nail-image-detection.ts";

const MAX_ORIGINAL_DIMENSION = 4096;
const SAMPLING_BUDGET_MS = 50;

/** 逐行复制构造超大图像，避免 16M 次逐像素回调拖慢测试。 */
function makeLargeImage(size: number): ImagePixels {
  const rowBytes = size * 4;
  const row = new Uint8ClampedArray(rowBytes);
  for (let x = 0; x < size; x += 1) {
    const offset = x * 4;
    row[offset] = 220;
    row[offset + 1] = 180;
    row[offset + 2] = 160;
    row[offset + 3] = 255;
  }
  const data = new Uint8ClampedArray(size * rowBytes);
  for (let y = 0; y < size; y += 1) {
    data.set(row, y * rowBytes);
  }
  return { width: size, height: size, data };
}

function candidates(): NailTextureCandidate[] {
  return [0, 1, 2, 3, 4].map((index) => ({
    id: `c${index}`,
    cx: 400 + index * 700,
    cy: 2048,
    length: 600,
    width: 400,
    angle: Math.PI / 2,
    score: 0.9,
    confidence: "high" as const,
    source: "model" as const,
    suggestedFinger: index,
  }));
}

test("4096² 原图上甲周采样循环在 50ms 预算内（不含解码与 getImageData）", () => {
  const image = makeLargeImage(MAX_ORIGINAL_DIMENSION);
  const list = candidates();

  // 预热一次，避免把首次 JIT 编译计入预算。
  samplePeriNailSkin(image, list, { expectedCandidates: 5 });

  const started = performance.now();
  const sample = samplePeriNailSkin(image, list, { expectedCandidates: 5 });
  const elapsed = performance.now() - started;

  assert.ok(sample.sampleCount > 0, "采样点不应为 0");
  assert.ok(elapsed < SAMPLING_BUDGET_MS, `采样耗时 ${elapsed.toFixed(2)}ms 超过 ${SAMPLING_BUDGET_MS}ms 预算`);
});

test("采样只在候选包围盒附近取点，不扫全图", () => {
  const image = makeLargeImage(1024);
  const single = candidates()
    .slice(0, 1)
    .map((item) => ({ ...item, cx: 512, cy: 512, length: 300, width: 200 }));
  const sample = samplePeriNailSkin(image, single, { expectedCandidates: 1 });
  // 24 角向 × 3 径向 = 72 个采样点上界。
  assert.ok(sample.sampleCount <= 72, `sampleCount=${sample.sampleCount} 超出环采样上界`);
  assert.ok(sample.sampleCount > 0);
});
