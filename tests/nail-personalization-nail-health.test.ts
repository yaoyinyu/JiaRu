import assert from "node:assert/strict";
import test from "node:test";

import {
  analyzeNailHealthHeuristic,
  NAIL_HEALTH_WEIGHTS,
} from "../src/lib/nail-personalization/nail-health.ts";
import type { NailMask, NailTextureCandidate } from "../src/lib/nail-texture-recognition/types.ts";
import type { ImagePixels } from "../src/lib/nail-image-detection.ts";

const IMAGE_SIZE = 100;
const MASK_WIDTH = 40;
const MASK_HEIGHT = 80;
const MASK_ORIGIN_X = 30;
const MASK_ORIGIN_Y = 10;

function makeImage(fill: (x: number, y: number) => [number, number, number]): ImagePixels {
  const data = new Uint8ClampedArray(IMAGE_SIZE * IMAGE_SIZE * 4);
  for (let y = 0; y < IMAGE_SIZE; y += 1) {
    for (let x = 0; x < IMAGE_SIZE; x += 1) {
      const [r, g, b] = fill(x, y);
      const offset = (y * IMAGE_SIZE + x) * 4;
      data[offset] = r;
      data[offset + 1] = g;
      data[offset + 2] = b;
      data[offset + 3] = 255;
    }
  }
  return { width: IMAGE_SIZE, height: IMAGE_SIZE, data };
}

function makeMask(): NailMask {
  const data = new Uint8Array(MASK_WIDTH * MASK_HEIGHT).fill(255);
  return {
    width: MASK_WIDTH,
    height: MASK_HEIGHT,
    data,
    originX: MASK_ORIGIN_X,
    originY: MASK_ORIGIN_Y,
    scale: 1,
  };
}

function candidate(overrides: Partial<NailTextureCandidate> = {}): NailTextureCandidate {
  return {
    id: "c1",
    cx: 50,
    cy: 50,
    length: 80,
    width: 40,
    angle: Math.PI / 2,
    score: 0.9,
    confidence: "high",
    source: "model",
    suggestedFinger: 1,
    mask: makeMask(),
    ...overrides,
  };
}

test("无 mask 候选时返回 null（当前 fallback 路径恒为 null）", () => {
  const image = makeImage(() => [180, 150, 130]);
  const noMask = candidate();
  delete (noMask as { mask?: NailMask }).mask;
  assert.equal(analyzeNailHealthHeuristic(image, [noMask]), null);
  assert.equal(analyzeNailHealthHeuristic(image, []), null);
});

test("均匀甲面：高均匀度、零高光、零条纹，得分 100", () => {
  const image = makeImage(() => [180, 150, 130]);
  const health = analyzeNailHealthHeuristic(image, [candidate()]);
  assert.ok(health, "应返回启发式结果");
  assert.equal(health.colorUniformity, 1);
  assert.equal(health.highlightRatio, 0);
  assert.equal(health.textureStreaking, 0);
  assert.equal(health.score, 100);
});

test("高光甲面：highlightRatio 拉满并拉低得分", () => {
  const image = makeImage(() => [255, 255, 255]);
  const health = analyzeNailHealthHeuristic(image, [candidate()]);
  assert.ok(health);
  assert.equal(health.highlightRatio, 1);
  assert.equal(health.score, 70);
});

test("纵向条纹甲面：streaking 升高并拉低得分", () => {
  const image = makeImage((x) => ((x % 8 < 4 ? [60, 60, 60] : [220, 220, 220]) as [number, number, number]));
  const health = analyzeNailHealthHeuristic(image, [candidate()]);
  assert.ok(health);
  assert.equal(health.textureStreaking, 1);
  assert.ok(health.score < 100, `score=${health.score}`);
});

test("输出恒带 heuristicOnly，且权重常量与文档一致", () => {
  const image = makeImage(() => [180, 150, 130]);
  const health = analyzeNailHealthHeuristic(image, [candidate()]);
  assert.ok(health);
  assert.equal(health.heuristicOnly, true);
  assert.equal(NAIL_HEALTH_WEIGHTS.uniformity, 0.5);
  assert.equal(NAIL_HEALTH_WEIGHTS.highlight, 0.3);
  assert.equal(NAIL_HEALTH_WEIGHTS.streaking, 0.2);
  const sum = NAIL_HEALTH_WEIGHTS.uniformity + NAIL_HEALTH_WEIGHTS.highlight + NAIL_HEALTH_WEIGHTS.streaking;
  assert.ok(Math.abs(sum - 1) < 1e-9);
});

test("mask 前景为空时返回 null", () => {
  const image = makeImage(() => [180, 150, 130]);
  const empty = candidate();
  empty.mask = { ...makeMask(), data: new Uint8Array(MASK_WIDTH * MASK_HEIGHT) };
  assert.equal(analyzeNailHealthHeuristic(image, [empty]), null);
});

test("前景像素过少时出 insufficient_foreground 警告", () => {
  const image = makeImage(() => [180, 150, 130]);
  const small = candidate();
  const data = new Uint8Array(MASK_WIDTH * MASK_HEIGHT);
  for (let index = 0; index < 10; index += 1) data[index] = 255;
  small.mask = { ...makeMask(), data };
  const health = analyzeNailHealthHeuristic(image, [small]);
  assert.ok(health);
  assert.ok(health.warnings.includes("nail_health_insufficient_foreground"));
});
