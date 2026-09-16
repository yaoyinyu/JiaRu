import assert from "node:assert/strict";
import test from "node:test";

import {
  PREVIEW_MAX_W,
  STROKE_STEP,
  interpolateStrokePoints,
  previewScale,
  scaleStroke,
  strokeDots,
  type Stroke,
} from "../src/lib/canvas/strokes.ts";
import { releaseRemovedBitmaps } from "../src/lib/ar-texture-release.ts";

/**
 * 2026-09-05 评审 #8/#9 修复的行为回归：
 *  - 编辑器笔画纯逻辑：预览缩放、插值与重放（显示/输出分离、重置=原图基线）；
 *  - AR 共享纹理释放：唯一集合 diff，多指共享不再泄漏。
 */

// ── 预览缩放 ──

test("previewScale：大图缩到 400×600 内，小图不放大", () => {
  assert.equal(previewScale(4096, 4096), PREVIEW_MAX_W / 4096);
  assert.equal(previewScale(800, 1200), 0.5); // min(400/800, 600/1200, 1)
  assert.equal(previewScale(1200, 800), PREVIEW_MAX_W / 1200); // 宽受限
  assert.equal(previewScale(300, 200), 1);
  assert.equal(previewScale(0, 100), 1); // 非法尺寸兜底
});

// ── 插值 ──

test("interpolateStrokePoints：步长语义与旧实现逐点一致", () => {
  // dist=10, step=5 → steps=2 → 3 点（含两端）
  assert.deepEqual(interpolateStrokePoints({ x: 0, y: 0 }, { x: 10, y: 0 }, 5), [
    { x: 0, y: 0 },
    { x: 5, y: 0 },
    { x: 10, y: 0 },
  ]);
  // dist<step → steps=1 → 两端点
  assert.deepEqual(interpolateStrokePoints({ x: 0, y: 0 }, { x: 3, y: 0 }, 5), [
    { x: 0, y: 0 },
    { x: 3, y: 0 },
  ]);
  // 同点 → steps=max(0,1)=1 → 两端点各一次（与旧实现语义一致：重复画同一点）
  assert.deepEqual(interpolateStrokePoints({ x: 2, y: 2 }, { x: 2, y: 2 }, 5), [
    { x: 2, y: 2 },
    { x: 2, y: 2 },
  ]);
});

// ── 缩放与重放 ──

const stroke: Stroke = {
  color: "#E8A0BF",
  size: 6,
  points: [
    { x: 0, y: 0 },
    { x: 100, y: 0 },
  ],
};

test("scaleStroke：点坐标与笔刷半径等比缩放", () => {
  const scaled = scaleStroke(stroke, 10.24);
  assert.equal(scaled.color, "#E8A0BF");
  assert.equal(scaled.size, 6 * 10.24);
  assert.equal(scaled.points[1].x, 100 * 10.24);
});

test("strokeDots：重放点数与缩放倍率无关（step 等比放大）", () => {
  const previewDots = strokeDots(stroke, 1, STROKE_STEP);
  const outScale = 4096 / 400;
  const exportDots = strokeDots(stroke, outScale, STROKE_STEP * outScale);
  assert.equal(exportDots.length, previewDots.length);
  // 首点与末点落在缩放后的端点上
  assert.equal(exportDots[0].x, 0);
  assert.equal(exportDots[exportDots.length - 1].x, 100 * outScale);
});

test("strokeDots：空笔画与单点笔画", () => {
  assert.deepEqual(strokeDots({ color: "#000", size: 4, points: [] }, 1, 5), []);
  const single = strokeDots({ color: "#000", size: 4, points: [{ x: 5, y: 5 }] }, 2, 5);
  assert.deepEqual(single, [{ x: 10, y: 10 }]);
});

test("strokeDots：预览与导出点集几何相似（对应点坐标成同一比例）", () => {
  const long: Stroke = {
    color: "#fff",
    size: 3,
    points: [
      { x: 0, y: 0 },
      { x: 30, y: 40 },
      { x: 90, y: 40 },
    ],
  };
  const outScale = 2.5;
  const preview = strokeDots(long, 1, STROKE_STEP);
  const out = strokeDots(long, outScale, STROKE_STEP * outScale);
  assert.equal(preview.length, out.length);
  for (let i = 0; i < preview.length; i++) {
    assert.ok(Math.abs(out[i].x - preview[i].x * outScale) < 1e-9);
    assert.ok(Math.abs(out[i].y - preview[i].y * outScale) < 1e-9);
  }
});

// ── AR 共享纹理释放（评审 #9 复现场景） ──

function fakeBitmap(label: string) {
  const bmp = {
    label,
    closed: false,
    close: () => {
      bmp.closed = true;
    },
  };
  return bmp;
}

test("releaseRemovedBitmaps：评审复现——A 四指共享、B 应用全部后 A 恰好释放一次", () => {
  const a = fakeBitmap("A");
  const b = fakeBitmap("B");
  const previous = [a, a, a, a, b]; // A 被四指共享，第五指为 B
  const next = [b, b, b, b, b]; // B 应用全部

  releaseRemovedBitmaps(previous, next);

  assert.equal(a.closed, true, "A 无槽位引用后必须被释放（旧实现 close 0 次）");
  assert.equal(b.closed, false, "B 仍被全部槽位保留，不得关闭");
});

test("releaseRemovedBitmaps：保留引用不关闭、重复引用只关闭一次", () => {
  const a = fakeBitmap("A");
  const b = fakeBitmap("B");
  const c = fakeBitmap("C");

  // A 保留在槽 0，B 与 C 被移除；B 在旧数组重复出现两次只 close 一次
  releaseRemovedBitmaps([b, a, b, c, null], [a, null, null, null, null]);

  assert.equal(a.closed, false);
  assert.equal(b.closed, true);
  assert.equal(c.closed, true);
});

test("releaseRemovedBitmaps：空数组与全保留", () => {
  const a = fakeBitmap("A");
  releaseRemovedBitmaps([], [a]);
  releaseRemovedBitmaps([a, a], [a]);
  assert.equal(a.closed, false, "无移除时不触发任何 close");
  releaseRemovedBitmaps([a], []);
  assert.equal(a.closed, true, "清空后必须释放");
});
