import assert from "node:assert/strict";
import test from "node:test";

import {
  alphaGridFromRgba,
  computeScaleToMaxEdge,
  downsampleAlphaGrid,
  nailMaskFromAlphaGrid,
  refineCandidateMasksWithMatte,
  type AlphaGrid,
} from "../src/lib/nail-texture-recognition/vlm-refinement.ts";
import { buildFeatheredAlphaMask } from "../src/lib/nail-texture-recognition/extract-mask-texture.ts";
import type { NailMask, NailTextureCandidate } from "../src/lib/nail-texture-recognition/types.ts";

/** 构造 RGBA：R 通道为灰度，A 恒 255（模拟 canvas 解码单通道 PNG 的真实行为）。 */
function rgbaFromGray(values: number[]): Uint8ClampedArray {
  const rgba = new Uint8ClampedArray(values.length * 4);
  values.forEach((value, index) => {
    rgba[index * 4] = value;
    rgba[index * 4 + 1] = value;
    rgba[index * 4 + 2] = value;
    rgba[index * 4 + 3] = 255;
  });
  return rgba;
}

test("灰度取 R 通道：A=255 不会被误当作前景", () => {
  const grid = alphaGridFromRgba(rgbaFromGray([200, 0, 130, 10]), 2, 2);
  assert.deepEqual(Array.from(grid.alpha), [200, 0, 130, 10]);
  assert.deepEqual(Array.from(grid.data), [1, 0, 1, 0]);
});

test("阈值边界：127 为背景、128 为前景", () => {
  const grid = alphaGridFromRgba(rgbaFromGray([127, 128]), 2, 1);
  assert.deepEqual(Array.from(grid.data), [0, 1]);
});

test("computeScaleToMaxEdge：只缩不放", () => {
  assert.equal(computeScaleToMaxEdge(3200, 1600, 1600), 0.5);
  assert.equal(computeScaleToMaxEdge(800, 600, 1600), 1);
  assert.equal(computeScaleToMaxEdge(0, 0, 1600), 1);
});

test("降采样：面积平均后重算二值几何", () => {
  // 4x4 → 2x2，每个目标像素由 2x2 平均
  const values = new Array(16).fill(0);
  values[0] = 255;
  values[1] = 255;
  values[4] = 255;
  values[5] = 255; // 左上 2x2 全 255
  const grid: AlphaGrid = {
    width: 4,
    height: 4,
    alpha: new Uint8ClampedArray(values),
    data: new Uint8Array(values.map((value) => (value >= 128 ? 1 : 0))),
  };

  const down = downsampleAlphaGrid(grid, 2);
  assert.equal(down.width, 2);
  assert.equal(down.height, 2);
  assert.equal(down.alpha[0], 255);
  assert.equal(down.alpha[1], 0);
  assert.equal(down.data[0], 1);
  assert.equal(down.data[1], 0);
});

test("不做放大的降采样直接返回原栅格", () => {
  const grid: AlphaGrid = {
    width: 10,
    height: 5,
    alpha: new Uint8ClampedArray(50).fill(100),
    data: new Uint8Array(50).fill(1),
  };
  assert.equal(downsampleAlphaGrid(grid, 1024), grid);
});

test("NailMask 口径：origin 0、scale 取宽高比例的较大者", () => {
  const grid: AlphaGrid = {
    width: 100,
    height: 100,
    alpha: new Uint8ClampedArray(10000).fill(255),
    data: new Uint8Array(10000).fill(1),
  };
  const mask = nailMaskFromAlphaGrid(grid, 800, 600);
  assert.equal(mask.originX, 0);
  assert.equal(mask.originY, 0);
  assert.equal(mask.scale, 8);
  assert.equal(mask.width, 100);
  assert.equal(mask.alpha, grid.alpha);
});

test("羽化合并：软 alpha 只能收紧边缘，不能扩张几何", () => {
  const width = 5;
  const height = 5;
  const base: NailMask = {
    width,
    height,
    data: new Uint8Array(width * height).fill(1),
    originX: 0,
    originY: 0,
    scale: 1,
  };

  const baseline = buildFeatheredAlphaMask(base, 2);
  // 无 alpha 时保持既有行为（本用例中心点为全不透明，角点为斜坡值）
  assert.equal(baseline[2 * width + 2], 255);
  assert.ok(baseline[0] > 0 && baseline[0] < 255);

  const soft = new Uint8ClampedArray(width * height).fill(255);
  soft[2 * width + 2] = 100;
  soft[0] = 255;
  const merged = buildFeatheredAlphaMask({ ...base, alpha: soft }, 2);
  assert.equal(merged[2 * width + 2], 100, "软边更小时应取软边");
  assert.equal(merged[0], baseline[0], "软边更大时不扩张");

  const transparent = buildFeatheredAlphaMask(
    { ...base, alpha: new Uint8ClampedArray(width * height) },
    2
  );
  assert.equal(Math.max(...Array.from(transparent)), 0, "软边为 0 时整块透明");
});

test("软 alpha 长度不符时整体忽略，不产生 NaN 或静默全透明", () => {
  const base: NailMask = {
    width: 3,
    height: 3,
    data: new Uint8Array(9).fill(1),
    originX: 0,
    originY: 0,
    scale: 1,
  };
  const baseline = Array.from(buildFeatheredAlphaMask(base, 1));
  const mismatched = Array.from(
    buildFeatheredAlphaMask({ ...base, alpha: new Uint8ClampedArray(2).fill(0) }, 1)
  );
  assert.deepEqual(mismatched, baseline);
});

function makeCandidate(id: string, cx: number): NailTextureCandidate {
  return {
    id,
    cx,
    cy: 100,
    length: 40,
    width: 20,
    angle: 0,
    score: 0.4,
    confidence: "low",
    source: "mediapipe",
    suggestedFinger: null,
  };
}

function smallGrid(): AlphaGrid {
  const grid: AlphaGrid = {
    width: 4,
    height: 4,
    alpha: new Uint8ClampedArray(16).fill(255),
    data: new Uint8Array(16).fill(1),
  };
  return grid;
}

test("refine 编排：只返回命中候选的 mask，未命中保留原结果", async () => {
  const candidates = [makeCandidate("a", 100), makeCandidate("b", 300)];
  const outcome = await refineCandidateMasksWithMatte({
    image: {} as CanvasImageSource,
    imageWidth: 400,
    imageHeight: 200,
    candidates,
    encode: async () => "data:image/jpeg;base64,AAAA",
    decode: async () => smallGrid(),
    request: async () => ({
      status: "ok",
      result: {
        width: 400,
        height: 200,
        instanceCount: 0,
        instances: [
          {
            index: 0,
            box: [82, 92, 118, 108],
            bbox: [84, 94, 116, 106],
            area: 500,
            alphaPng: "data:image/png;base64,AAAA",
            width: 400,
            height: 200,
          },
        ],
        omittedInstances: 0,
        model: "m",
        quant: "int4",
        elapsedMs: 12000,
      },
    } as never),
  });

  assert.equal(outcome.status, "ok");
  if (outcome.status !== "ok") return;
  assert.equal(outcome.matchedCount, 1);
  assert.equal(outcome.masks[0].candidateId, "a");
  assert.equal(outcome.candidateCount, 2);
  assert.ok(outcome.warnings.includes("matte_partial_match"));
  assert.equal(outcome.masks[0].mask.width, 4);
});

test("refine 编排：无实例时返回 0 命中并给出警告，不伪造匹配", async () => {
  const outcome = await refineCandidateMasksWithMatte({
    image: {} as CanvasImageSource,
    imageWidth: 400,
    imageHeight: 200,
    candidates: [makeCandidate("a", 100)],
    encode: async () => "data:image/jpeg;base64,AAAA",
    decode: async () => smallGrid(),
    request: async () => ({
      status: "ok",
      result: {
        width: 400,
        height: 200,
        instances: [],
        omittedInstances: 0,
        model: "m",
        quant: "int4",
        elapsedMs: 9000,
      },
    } as never),
  });

  assert.equal(outcome.status, "ok");
  if (outcome.status !== "ok") return;
  assert.equal(outcome.matchedCount, 0);
  assert.ok(outcome.warnings.includes("matte_no_instances"));
});

test("refine 编排：降级结果原样透传，不产生 mask", async () => {
  const outcome = await refineCandidateMasksWithMatte({
    image: {} as CanvasImageSource,
    imageWidth: 400,
    imageHeight: 200,
    candidates: [makeCandidate("a", 100)],
    encode: async () => "data:image/jpeg;base64,AAAA",
    decode: async () => smallGrid(),
    request: async () => ({
      status: "degraded",
      reason: "busy",
      message: "抠图服务正在处理其他图片",
      retryAfterSeconds: 3,
    }),
  });

  assert.equal(outcome.status, "degraded");
  if (outcome.status !== "degraded") return;
  assert.equal(outcome.reason, "busy");
  assert.equal(outcome.retryAfterSeconds, 3);
});
