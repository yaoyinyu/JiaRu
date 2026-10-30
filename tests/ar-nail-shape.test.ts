import assert from "node:assert/strict";
import test from "node:test";

import {
  computeTextureRenderPlan,
  glossToRenderFactor,
  getNailShapeProfile,
  ROUND_ROOT_BULGE,
  ROUND_SIDE_CURVE,
  ROUND_TIP_NARROW,
} from "../src/lib/ar-nail-shape.ts";

test("getNailShapeProfile：round 档与历史硬编码常量逐字段一致", () => {
  for (let finger = 0; finger < 5; finger += 1) {
    const profile = getNailShapeProfile("round", finger);
    assert.equal(profile.tipNarrow, ROUND_TIP_NARROW[finger], `finger ${finger} tipNarrow`);
    assert.equal(profile.sideCurve, ROUND_SIDE_CURVE[finger], `finger ${finger} sideCurve`);
    assert.equal(profile.rootBulge, ROUND_ROOT_BULGE[finger], `finger ${finger} rootBulge`);
    assert.equal(profile.tipArch, 0.15);
    assert.equal(profile.sideFlare, 0.3);

    // null / undefined 同样落到 round 档（未传 nailStyles 时渲染不变的回归保护）
    const fallback = getNailShapeProfile(null, finger);
    assert.deepEqual(fallback, profile);
  }
});

test("getNailShapeProfile：方/杏仁/尖的几何特征符合甲型语义", () => {
  const square = getNailShapeProfile("square", 2);
  const almond = getNailShapeProfile("almond", 2);
  const stiletto = getNailShapeProfile("stiletto", 2);

  // 尖端开口宽度：方甲接近全宽，杏仁收窄，尖甲近似收成一点
  assert.ok(square.tipNarrow < almond.tipNarrow);
  assert.ok(almond.tipNarrow < stiletto.tipNarrow);
  // 尖端拱度：方甲最平，尖甲接近直线收点，圆拱最大的是 round
  const round = getNailShapeProfile("round", 2);
  assert.ok(square.tipArch < almond.tipArch);
  assert.ok(stiletto.tipArch < square.tipArch);
  assert.ok(almond.tipArch < round.tipArch);
  // 侧线：方甲最直，尖甲锥化控制点最长
  assert.ok(square.sideCurve < almond.sideCurve);
  assert.ok(almond.sideCurve < stiletto.sideCurve);
  // 根部凸起保留逐指常量
  for (const shape of ["square", "almond", "stiletto"] as const) {
    assert.equal(getNailShapeProfile(shape, 3).rootBulge, ROUND_ROOT_BULGE[3]);
  }
});

test("computeTextureRenderPlan：长宽比保真且甲根锚定、向甲尖延伸", () => {
  // 竖直甲面（甲尖朝上）：angle = 0，甲尖方向 = (sin0, -cos0) = (0, -1) = 屏幕上方
  const geometry = { cx: 100, cy: 200, length: 50, width: 30, angle: 0 };
  const plan = computeTextureRenderPlan(geometry, 2.0);
  // 渲染长度 = 宽度 × 纹理长宽比 = 60（比估算 50 更长）
  assert.ok(Math.abs(plan.length - 60) < 1e-9);
  // 中心向甲尖（上方）移动 (60-50)/2 = 5 → 甲根边缘 200+25 保持不动，甲尖伸出
  assert.ok(Math.abs(plan.cx - 100) < 1e-9);
  assert.ok(Math.abs(plan.cy - 195) < 1e-9);
  assert.ok(Math.abs(plan.cy + plan.length / 2 - (geometry.cy + geometry.length / 2)) < 1e-9,
    "甲根边缘应锚定不动");
});

test("computeTextureRenderPlan：横轴旋转时延伸方向跟随甲尖方向", () => {
  // 甲尖指向右侧（指尖方向 (+1,0) → 横轴 angle = π/2），甲尖方向 = (sin(π/2), -cos(π/2)) = (1, 0)
  const geometry = { cx: 100, cy: 200, length: 50, width: 30, angle: Math.PI / 2 };
  const plan = computeTextureRenderPlan(geometry, 1.6); // 渲染长度 48 < 50
  assert.ok(Math.abs(plan.length - 50) < 1e-9, "纹理比估算短时保持估算长度（盖满真实甲面）");
  assert.ok(Math.abs(plan.cx - 100) < 1e-9);
  assert.ok(Math.abs(plan.cy - 200) < 1e-9);

  const longPlan = computeTextureRenderPlan(geometry, 3.0); // 渲染长度 90 > 50
  assert.ok(Math.abs(longPlan.length - 90) < 1e-9);
  assert.ok(Math.abs(longPlan.cx - 120) < 1e-9, "中心应向甲尖（+x）移动 20");
  assert.ok(Math.abs(longPlan.cy - 200) < 1e-9);
});

test("computeTextureRenderPlan：极端长宽比受上限约束，非法比例退回估算长度", () => {
  const geometry = { cx: 0, cy: 0, length: 50, width: 30, angle: 0 };
  // 长宽比 6 → 180 超过上限 3×50=150 → 取 150
  const capped = computeTextureRenderPlan(geometry, 6.0);
  assert.ok(Math.abs(capped.length - 150) < 1e-9);
  assert.ok(
    Math.abs(capped.cy + capped.length / 2 - (geometry.cy + geometry.length / 2)) < 1e-9,
    "甲根边缘仍锚定在 cy+25"
  );

  // 非法比例 → 退回估算长度，几何不动
  for (const aspect of [Number.NaN, 0, -2]) {
    const fallback = computeTextureRenderPlan(geometry, aspect);
    assert.ok(Math.abs(fallback.length - 50) < 1e-9);
    assert.ok(Math.abs(fallback.cx) < 1e-9);
    assert.ok(Math.abs(fallback.cy) < 1e-9);
  }
});

test("glossToRenderFactor：未提供为 1，两端钳制且单调", () => {
  assert.equal(glossToRenderFactor(null), 1);
  assert.equal(glossToRenderFactor(undefined), 1);
  assert.equal(glossToRenderFactor(Number.NaN), 1);
  assert.equal(glossToRenderFactor(0), 0.55);
  assert.equal(glossToRenderFactor(1), 1.35);
  assert.equal(glossToRenderFactor(0.5), 0.55 + 0.4, "0.55 + 0.5*0.8（浮点按同式计算）");
  // 越界钳制
  assert.equal(glossToRenderFactor(-1), 0.55);
  assert.equal(glossToRenderFactor(2), 1.35);
  // 单调
  let previous = -Infinity;
  for (let gloss = 0; gloss <= 1.001; gloss += 0.1) {
    const factor = glossToRenderFactor(gloss);
    assert.ok(factor >= previous);
    previous = factor;
  }
});
