import assert from "node:assert/strict";
import test from "node:test";
import {
  bboxFromLandmarks,
  expandRoi,
  remapLandmarks,
  roiSanity,
  segBootstrapBox,
} from "../src/lib/ar-roi-tracking.ts";

test("包围盒外扩并夹取到 [0,1]", () => {
  const lm = [
    { x: 0.02, y: 0.1, z: 0 },
    { x: 0.5, y: 0.4, z: 0 },
    { x: 0.98, y: 0.9, z: 0 },
  ];
  const box = bboxFromLandmarks(lm, 0.08);
  assert.ok(box);
  assert.equal(box.x, 0);
  assert.ok(box.y >= 0 && box.y <= 0.0200001);
  assert.ok(box.x + box.w <= 1);
  assert.ok(box.y + box.h <= 1);
});

test("空关键点返回 null", () => {
  assert.equal(bboxFromLandmarks([]), null);
});

test("裁剪窗夹取到源尺寸且不小于 8px", () => {
  const box = { x: 0.4, y: 0.4, w: 0.2, h: 0.2 };
  const crop = expandRoi(box, 640, 480, 1.35);
  assert.ok(crop);
  assert.ok(crop.sx >= 0 && crop.sy >= 0);
  assert.ok(crop.sx + crop.sw <= 640);
  assert.ok(crop.sy + crop.sh <= 480);
  assert.ok(crop.sw >= 8 && crop.sh >= 8);
});

test("裁剪窗内关键点映射回全帧归一化", () => {
  const crop = { sx: 100, sy: 50, sw: 200, sh: 200 };
  const remapped = remapLandmarks([{ x: 0.5, y: 0.5, z: 0.1 }], crop, 640, 480);
  assert.ok(Math.abs(remapped[0].x - 200 / 640) < 1e-9);
  assert.ok(Math.abs(remapped[0].y - 150 / 480) < 1e-9);
  assert.equal(remapped[0].z, 0.1);
});

test("冷启动 bootstrap：粗分割实例并集外扩，低分实例剔除，空集返回 null", () => {
  const box = segBootstrapBox([
    { cx: 0.5, cy: 0.4, w: 0.1, h: 0.1, score: 0.8 },
    { cx: 0.6, cy: 0.45, w: 0.1, h: 0.1, score: 0.7 },
    { cx: 0.1, cy: 0.1, w: 0.1, h: 0.1, score: 0.1 },
  ]);
  assert.ok(box);
  assert.ok(box.x <= 0.45 && box.x + box.w >= 0.65);
  assert.ok(box.y <= 0.35 && box.y + box.h >= 0.5);
  assert.ok(box.x >= 0.3 && box.y >= 0.2);
  assert.equal(segBootstrapBox([]), null);
  assert.equal(segBootstrapBox([{ cx: 0.5, cy: 0.5, w: 0.1, h: 0.1, score: 0.1 }]), null);
});

test("漂移守卫：质心在上一帧包围盒外扩域内且跨度合理才通过", () => {
  const prev = { x: 0.3, y: 0.3, w: 0.3, h: 0.3 };
  const good = [
    { x: 0.35, y: 0.35, z: 0 },
    { x: 0.5, y: 0.5, z: 0 },
    { x: 0.55, y: 0.55, z: 0 },
  ];
  assert.equal(roiSanity(good, prev), true);
  const drifted = good.map(p => ({ ...p, x: p.x + 0.6, y: p.y + 0.6 }));
  assert.equal(roiSanity(drifted, prev), false);
  assert.equal(roiSanity([], prev), false);
});