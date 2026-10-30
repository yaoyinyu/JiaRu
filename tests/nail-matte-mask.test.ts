import assert from "node:assert/strict";
import test from "node:test";

import {
  alphaGridFromRgba,
  candidateFromMatteInstance,
  computeMatteEncodeGeometry,
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

test("computeMatteEncodeGeometry：与编码器同口径的长边换算", () => {
  assert.deepEqual(computeMatteEncodeGeometry(1200, 1499), {
    scale: 1,
    width: 1200,
    height: 1499,
  });
  assert.deepEqual(computeMatteEncodeGeometry(3200, 2400), {
    scale: 0.5,
    width: 1600,
    height: 1200,
  });
  assert.deepEqual(computeMatteEncodeGeometry(800, 600), {
    scale: 1,
    width: 800,
    height: 600,
  });
});

test("refine 编排：大图候选框换算到编码空间后可正常匹配", async () => {
  // 原图 3200×2400 → 编码 1600×1200（scale 0.5）。
  // 候选框在原图坐标（旋转外接框 [1550,1100,1650,1300]），编码后 [775,550,825,650]；
  // 上游实例框固定在编码坐标系。修复前两侧坐标域不一致 → IoU 0 且中心不落框 → 0 命中。
  const candidates = [makeCandidate("a", 1600)];
  const candidate = candidates[0];
  candidate.cy = 1200;
  candidate.length = 200;
  candidate.width = 100;

  const outcome = await refineCandidateMasksWithMatte({
    image: {} as CanvasImageSource,
    imageWidth: 3200,
    imageHeight: 2400,
    candidates,
    encode: async () => "data:image/jpeg;base64,AAAA",
    decode: async () => smallGrid(),
    request: async () => ({
      status: "ok",
      result: {
        width: 1600,
        height: 1200,
        instanceCount: 1,
        instances: [
          {
            index: 0,
            box: [780, 555, 822, 648],
            bbox: [782, 557, 820, 646],
            area: 5000,
            alphaPng: "data:image/png;base64,AAAA",
            width: 1600,
            height: 1200,
          },
        ],
        omittedInstances: 0,
        model: "m",
        quant: "int4",
        elapsedMs: 14000,
      },
    } as never),
  });

  assert.equal(outcome.status, "ok");
  if (outcome.status !== "ok") return;
  assert.equal(outcome.matchedCount, 1);
  assert.equal(outcome.masks[0].candidateId, "a");
  assert.deepEqual(outcome.warnings, []);
  assert.equal(outcome.masks[0].mask.width, 4);
  // 掩膜回映射原图口径不变：整图栅格按原图尺寸取 scale
  assert.equal(outcome.masks[0].mask.scale, Math.max(3200 / 4, 2400 / 4));
});

function normalizeAngleDelta(delta: number): number {
  let result = delta;
  while (result > Math.PI) result -= Math.PI * 2;
  while (result <= -Math.PI) result += Math.PI * 2;
  return result;
}

function buildTiltedAlphaGrid(
  width: number,
  height: number,
  tipAngle: number
): AlphaGrid {
  const alpha = new Uint8ClampedArray(width * height);
  const data = new Uint8Array(width * height);
  const cx = width / 2;
  const cy = height / 2;
  const longRadius = width * 0.38;
  const shortRadius = width * 0.16;
  const tipX = Math.cos(tipAngle);
  const tipY = Math.sin(tipAngle);
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      const dx = x - cx;
      const dy = y - cy;
      const along = dx * tipX + dy * tipY;
      const across = -dx * tipY + dy * tipX;
      const ratio =
        (along / longRadius) * (along / longRadius) +
        (across / shortRadius) * (across / shortRadius);
      if (ratio <= 1) {
        alpha[y * width + x] = 255;
        data[y * width + x] = 1;
      }
    }
  }
  return { width, height, alpha, data };
}

test("candidateFromMatteInstance：角度取 alpha 主轴而非固定 0", () => {
  // 长轴指向 π/2+0.3，横轴半转角应为 0.3
  const grid = buildTiltedAlphaGrid(24, 24, Math.PI / 2 + 0.3);
  const candidate = candidateFromMatteInstance(
    {
      index: 0,
      box: [2, 2, 22, 22],
      bbox: [3, 3, 21, 21],
      area: 200,
      alphaPng: "data:image/png;base64,AAAA",
      width: 100,
      height: 100,
    },
    grid,
    100,
    100
  );

  assert.equal(candidate.source, "vlm-matte");
  assert.equal(candidate.confidence, "low");
  assert.ok(
    Math.abs(normalizeAngleDelta(candidate.angle - 0.3)) < 0.06,
    `候选角度应取主轴 0.3，实际 ${candidate.angle}`
  );
  assert.equal(candidate.mask?.width, 24);
});

test("candidateFromMatteInstance：候选几何落在原图坐标域（长边 >1600 图）", () => {
  // 模拟 12MP 手机照片：原图 3200x2400，编码图 1600x1200（scale 0.5），
  // alpha 栅格为整图等比降采样（80x60）。实心块在栅格 x 20..34、y 10..19，
  // 按提取同口径逐轴映射回原图应为 cx=1100、cy=600、width=600、length=400。
  const width = 80;
  const height = 60;
  const alpha = new Uint8ClampedArray(width * height);
  const data = new Uint8Array(width * height);
  for (let y = 10; y <= 19; y += 1) {
    for (let x = 20; x <= 34; x += 1) {
      alpha[y * width + x] = 255;
      data[y * width + x] = 1;
    }
  }
  const grid: AlphaGrid = { width, height, alpha, data };
  const candidate = candidateFromMatteInstance(
    {
      index: 0,
      // 上游 box/bbox 在编码图（1600x1200）坐标域；若被误当作原图坐标，
      // 中心会是 (140,110)，叠加层整体缩聚到左上角。
      box: [100, 80, 180, 140],
      bbox: [102, 82, 178, 138],
      area: 150,
      alphaPng: "data:image/png;base64,AAAA",
      width: 1600,
      height: 1200,
    },
    grid,
    3200,
    2400
  );

  assert.equal(candidate.cx, 1100);
  assert.equal(candidate.cy, 600);
  assert.equal(candidate.width, 600);
  assert.equal(candidate.length, 400);
  assert.equal(candidate.mask?.width, 80);
});

test("candidateFromMatteInstance：空栅格兜底按编码几何映射回原图", () => {
  const grid: AlphaGrid = {
    width: 4,
    height: 4,
    alpha: new Uint8ClampedArray(16),
    data: new Uint8Array(16),
  };
  const candidate = candidateFromMatteInstance(
    {
      index: 0,
      box: [100, 80, 180, 140],
      bbox: [0, 0, 0, 0],
      area: 0,
      alphaPng: "data:image/png;base64,AAAA",
      width: 4,
      height: 4,
    },
    grid,
    3200,
    2400
  );

  // 编码空间 (140,110) 除以 scale 0.5 → 原图 (280,220)；宽 80→160、长 60→120。
  assert.equal(candidate.cx, 280);
  assert.equal(candidate.cy, 220);
  assert.equal(candidate.width, 160);
  assert.equal(candidate.length, 120);
});
