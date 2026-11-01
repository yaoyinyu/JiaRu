import assert from "node:assert/strict";
import test from "node:test";

import {
  DEFAULT_PLACEMENT_ADJUST,
  PREVIEW_MAX_W,
  applyPlacementAdjust,
  buildPlacementFromFrame,
  frameHitTest,
  placementDrawList,
  placementHitTest,
  previewScale,
  type NailPlacement,
  type PlacementFrameInput,
} from "../src/lib/canvas/placements.ts";
import { releaseRemovedBitmaps } from "../src/lib/ar-texture-release.ts";

/**
 * 编辑器画布「甲面框 + 纹理贴合实例」模型回归（2026-10-31 重写，v1.2.173）：
 *  - placements 纯逻辑：贴合构建的长宽比保真/甲根锚定/3× 上限/非法 aspect 回退、
 *    微调重算（含甲根方向与钳制）、导出重放缩放、旋转椭圆命中（末尾优先）；
 *  - 预览缩放沿用旧笔刷画布 400×600 口径（函数迁入 placements.ts）；
 *  - AR 共享纹理释放：唯一集合 diff，多指共享不再泄漏（AR 页仍在用）。
 * 旧 strokes 笔画模块已随模型重写删除，相关断言一并移除。
 */

// ── 预览缩放 ──

test("previewScale：大图缩到 400×600 内，小图不放大", () => {
  assert.equal(previewScale(4096, 4096), PREVIEW_MAX_W / 4096);
  assert.equal(previewScale(800, 1200), 0.5); // min(400/800, 600/1200, 1)
  assert.equal(previewScale(1200, 800), PREVIEW_MAX_W / 1200); // 宽受限
  assert.equal(previewScale(300, 200), 1);
  assert.equal(previewScale(0, 100), 1); // 非法尺寸兜底
});

// ── 贴合构建：buildPlacementFromFrame ──

const FRAME: PlacementFrameInput = {
  id: "f1",
  cx: 100,
  cy: 100,
  angle: 0,
  nl: 50,
  nw: 40,
  assignedFinger: 2,
};
const TEX_2X1 = { key: "setA/3", src: "/nail-textures/setA/finger-3.png", aspect: 2 };

test("buildPlacementFromFrame：长宽比保真（合成 2:1 纹理 → length≈width×2 且 ≥ 框长）", () => {
  const p = buildPlacementFromFrame(FRAME, TEX_2X1);
  assert.equal(p.id, "placement-f1");
  assert.equal(p.frameId, "f1");
  assert.equal(p.textureKey, "setA/3");
  assert.equal(p.textureSrc, TEX_2X1.src);
  assert.equal(p.angle, 0);
  assert.equal(p.baseCx, 100);
  assert.equal(p.baseCy, 100);
  assert.equal(p.baseLength, 50);
  assert.equal(p.baseWidth, 40);
  assert.equal(p.width, 40);
  // width×aspect = 80，在钳制域内（≥nl=50 且 ≤3×50=150）
  assert.ok(Math.abs(p.length - 80) < 1e-9);
  assert.ok(p.length >= FRAME.nl);
  assert.ok(Math.abs(p.length - p.width * 2) < 1e-9);
  // 缺省微调
  assert.deepEqual(p.adjust, { lengthScale: 1, widthScale: 1, rootOffset: 0 });
  assert.deepEqual(DEFAULT_PLACEMENT_ADJUST, { lengthScale: 1, widthScale: 1, rootOffset: 0 });
});

test("buildPlacementFromFrame：甲根边缘锚定——延长部分沿甲尖（局部 −Y）伸出", () => {
  // angle=0：甲尖朝 −Y，渲染长 80 比框长 50 多 15，中心上移 15
  const upright = buildPlacementFromFrame({ ...FRAME, angle: 0 }, TEX_2X1);
  assert.ok(Math.abs(upright.cy - 85) < 1e-9, "甲根锚定：中心应向甲尖（−Y）移动");
  assert.equal(upright.cx, 100);

  // angle=π/2：局部 −Y 的世界方向为 +X，中心沿 +X 移动 15
  const sideways = buildPlacementFromFrame({ ...FRAME, angle: Math.PI / 2 }, TEX_2X1);
  assert.ok(Math.abs(sideways.cx - 115) < 1e-9, "甲根锚定：angle=90° 时甲尖朝 +X");
  assert.ok(Math.abs(sideways.cy - 100) < 1e-9);
  assert.ok(Math.abs(sideways.length - 80) < 1e-9);
});

test("buildPlacementFromFrame：渲染长上限 3× 框长", () => {
  const small: PlacementFrameInput = { id: "f2", cx: 0, cy: 0, angle: 0, nl: 30, nw: 100, assignedFinger: null };
  const capped = buildPlacementFromFrame(small, TEX_2X1);
  // width×aspect = 200 > 3×30 = 90 → 钳到 90（不短于框长 30）
  assert.ok(Math.abs(capped.length - 90) < 1e-9);
  assert.equal(capped.width, 100);
});

test("buildPlacementFromFrame：非法 aspect（NaN/0/负数/Infinity）回退为框长", () => {
  for (const aspect of [Number.NaN, 0, -3, Number.POSITIVE_INFINITY]) {
    const p = buildPlacementFromFrame(FRAME, { ...TEX_2X1, aspect });
    // safeAspect=1：min(40×1, 150)=40 → max(50, 40)=50（不短于框长）
    assert.ok(Math.abs(p.length - 50) < 1e-9, `aspect=${aspect} 应回退`);
    assert.equal(p.width, 40);
  }
});

// ── 微调重算：applyPlacementAdjust ──

const basePlacement = buildPlacementFromFrame(FRAME, TEX_2X1); // (100, 85) 80×40

test("applyPlacementAdjust：从 base 几何重算且不改入参", () => {
  const scaled = applyPlacementAdjust(basePlacement, { lengthScale: 1.2, widthScale: 1, rootOffset: 0 });
  assert.ok(Math.abs(scaled.length - 96) < 1e-9, "渲染长 80×1.2");
  assert.equal(scaled.width, 40);
  // rootOffset=0 时中心不动（长度变化围绕渲染计划中心）
  assert.ok(Math.abs(scaled.cx - 100) < 1e-9);
  assert.ok(Math.abs(scaled.cy - 85) < 1e-9);
  assert.deepEqual(scaled.adjust, { lengthScale: 1.2, widthScale: 1, rootOffset: 0 });
  // base 基准与原对象不受影响
  assert.equal(basePlacement.length, 80);
  assert.equal(basePlacement.cx, 100);
  assert.equal(basePlacement.cy, 85);
  assert.deepEqual(basePlacement.adjust, DEFAULT_PLACEMENT_ADJUST);
  assert.equal(scaled.baseLength, basePlacement.baseLength);
  assert.equal(scaled.aspect, basePlacement.aspect);
});

test("applyPlacementAdjust：rootOffset 正值沿甲根方向 (−sin(angle), cos(angle)) 移动", () => {
  // angle=0：甲根方向 (0, 1)（+Y，指向指根），位移 = 80×0.1 = 8
  const shifted = applyPlacementAdjust(basePlacement, { lengthScale: 1, widthScale: 1, rootOffset: 0.1 });
  assert.ok(Math.abs(shifted.cy - 93) < 1e-9, "甲根方向 +Y：cy = 85 + 8");
  assert.ok(Math.abs(shifted.cx - 100) < 1e-9);

  // angle=π/2：甲根方向 (−1, 0)（−X），中心从 115 移到 107
  const rotated = buildPlacementFromFrame({ ...FRAME, angle: Math.PI / 2 }, TEX_2X1);
  const shiftedRotated = applyPlacementAdjust(rotated, { lengthScale: 1, widthScale: 1, rootOffset: 0.1 });
  assert.ok(Math.abs(shiftedRotated.cx - 107) < 1e-9, "甲根方向 −X：cx = 115 − 8");
  assert.ok(Math.abs(shiftedRotated.cy - 100) < 1e-9);
});

test("applyPlacementAdjust：钳制 0.75–1.4 / 0.7–1.45 / ±0.2", () => {
  const extreme = applyPlacementAdjust(basePlacement, { lengthScale: 5, widthScale: 5, rootOffset: 5 });
  assert.ok(Math.abs(extreme.length - 80 * 1.4) < 1e-9, "lengthScale 钳到 1.4");
  assert.ok(Math.abs(extreme.width - 40 * 1.45) < 1e-9, "widthScale 钳到 1.45");
  assert.ok(Math.abs(extreme.cy - (85 + 80 * 0.2)) < 1e-9, "rootOffset 钳到 +0.2");
  assert.ok(Math.abs(extreme.cx - 100) < 1e-9);

  const tiny = applyPlacementAdjust(basePlacement, { lengthScale: 0.1, widthScale: 0.1, rootOffset: -5 });
  assert.ok(Math.abs(tiny.length - 80 * 0.75) < 1e-9);
  assert.ok(Math.abs(tiny.width - 40 * 0.7) < 1e-9);
  assert.ok(Math.abs(tiny.cy - (85 - 80 * 0.2)) < 1e-9);
});

// ── 导出重放：placementDrawList ──

test("placementDrawList：cx/cy/length/width 按 factor 等比缩放，angle 不变", () => {
  const rotated = buildPlacementFromFrame({ ...FRAME, angle: Math.PI / 3 }, TEX_2X1);
  const items = placementDrawList([basePlacement, rotated], 0.5);
  assert.equal(items.length, 2);
  assert.equal(items[0].textureSrc, TEX_2X1.src);
  assert.equal(items[0].angle, 0);
  assert.equal(items[1].angle, Math.PI / 3);
  assert.ok(Math.abs(items[0].cx - basePlacement.cx * 0.5) < 1e-12);
  assert.ok(Math.abs(items[0].cy - basePlacement.cy * 0.5) < 1e-12);
  assert.ok(Math.abs(items[0].length - basePlacement.length * 0.5) < 1e-12);
  assert.ok(Math.abs(items[0].width - basePlacement.width * 0.5) < 1e-12);
  assert.ok(Math.abs(items[1].cx - rotated.cx * 0.5) < 1e-12);
  // factor=1 恒等（贴合几何为原图像素域，原图尺寸导出画布用 1）
  const identity = placementDrawList([rotated], 1);
  assert.equal(identity[0].cx, rotated.cx);
  assert.equal(identity[0].length, rotated.length);
  // 空数组
  assert.deepEqual(placementDrawList([], 2), []);
});

// ── 命中测试 ──

function makePlacement(overrides: Partial<NailPlacement> & Pick<NailPlacement, "cx" | "cy" | "angle">): NailPlacement {
  return {
    id: "p",
    frameId: null,
    textureKey: "k",
    textureSrc: "/t.png",
    aspect: 1,
    baseCx: 0,
    baseCy: 0,
    baseLength: 10,
    baseWidth: 10,
    length: 80,
    width: 40,
    adjust: { lengthScale: 1, widthScale: 1, rootOffset: 0 },
    ...overrides,
  };
}

test("placementHitTest：旋转椭圆域与末尾优先", () => {
  const a = makePlacement({ id: "a", cx: 100, cy: 100, angle: 0 }); // 80×40，长轴沿局部 Y
  const b = makePlacement({ id: "b", cx: 120, cy: 100, angle: 0 }); // 与 a 重叠
  const placements = [a, b];

  assert.equal(placementHitTest(placements, 120, 100), 1, "命中 b 中心");
  assert.equal(placementHitTest(placements, 100, 130), 0, "命中 a 长轴内（|dy|=30 ≤ 40）");
  assert.equal(placementHitTest(placements, 100, 145), -1, "长轴外（|dy|=45 > 40）");
  assert.equal(placementHitTest(placements, 145, 100), -1, "两实例横轴均覆盖不到（b 的 |dx|=25 > 20）");
  // 重叠区命中末尾（顶层）实例
  assert.equal(placementHitTest(placements, 105, 100), 1);
  assert.equal(placementHitTest([a], 105, 100), 0);
  assert.equal(placementHitTest([], 100, 100), -1);

  // angle=π/2：长轴转到世界 X 方向
  const rotated = makePlacement({ id: "r", cx: 100, cy: 100, angle: Math.PI / 2 });
  assert.equal(placementHitTest([rotated], 130, 100), 0, "旋转后长轴沿 +X");
  assert.equal(placementHitTest([rotated], 100, 130), -1, "旋转后横轴沿 Y，30 > 20");
});

test("frameHitTest：椭圆域与末尾优先", () => {
  const f1: PlacementFrameInput = { id: "f1", cx: 50, cy: 50, angle: 0, nl: 40, nw: 30, assignedFinger: 1 };
  const f2: PlacementFrameInput = { id: "f2", cx: 60, cy: 50, angle: 0, nl: 40, nw: 30, assignedFinger: null };
  const frames = [f1, f2];

  assert.equal(frameHitTest(frames, 60, 50), 1);
  assert.equal(frameHitTest(frames, 40, 50), 0, "仅命中 f1（f2 的 |dx|=20 > 15）");
  assert.equal(frameHitTest(frames, 57, 50), 1, "重叠区命中末尾");
  assert.equal(frameHitTest(frames, 50, 75), -1, "长轴外（|dy|=25 > 20）");
  assert.equal(frameHitTest([], 50, 50), -1);

  // 旋转 90°：长轴沿世界 X
  const rotated: PlacementFrameInput = { id: "f3", cx: 0, cy: 0, angle: Math.PI / 2, nl: 40, nw: 20, assignedFinger: 4 };
  assert.equal(frameHitTest([rotated], 15, 0), 0, "旋转后长轴半长 20 沿 X");
  assert.equal(frameHitTest([rotated], 0, 15), -1, "旋转后横轴半长 10 沿 Y");
});

// ── AR 共享纹理释放（AR 页仍在用） ──

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
