import assert from "node:assert/strict";
import test from "node:test";
import {
  computeFingerNailOrientation,
  computeHandDorsumNormal,
  NAIL_FACING_COS,
  type Vec3,
} from "../src/lib/ar-nail-orientation.ts";
import { computeNailGeometry, NAIL_DIPS, NAIL_PIPS, NAIL_TIPS, type NailLandmark } from "../src/lib/nail-geometry.ts";

const Z = 1;

function joints(m3: Vec3, d3: Vec3, p3: Vec3 | null) {
  const pip = { x: 0.5, y: 0.45, z: 0 };
  const dip = { x: pip.x + m3.x, y: pip.y + m3.y, z: pip.z + m3.z };
  const tip = { x: dip.x + d3.x, y: dip.y + d3.y, z: dip.z + d3.z };
  const mcp = p3 ? { x: pip.x - p3.x, y: pip.y - p3.y, z: pip.z - p3.z } : undefined;
  return { tip, dip, pip, mcp };
}

function openHand(): NailLandmark[] {
  const points = Array.from({ length: 21 }, () => ({ x: 0.5, y: 0.5, z: 0 }));
  points[0] = { x: 0.5, y: 0.78, z: 0 };
  points[5] = { x: 0.38, y: 0.58, z: 0 };
  points[9] = { x: 0.5, y: 0.54, z: 0 };
  points[17] = { x: 0.62, y: 0.58, z: 0 };
  points[NAIL_PIPS[2]] = { x: 0.5, y: 0.45, z: 0 };
  points[NAIL_DIPS[2]] = { x: 0.5, y: 0.35, z: 0 };
  points[NAIL_TIPS[2]] = { x: 0.5, y: 0.25, z: 0 };
  return points;
}

test("手背法向符号随全局朝向定向", () => {
  const lm = openHand();
  const dorsum = computeHandDorsumNormal(lm, "dorsum", -0.01, Z);
  const palm = computeHandDorsumNormal(lm, "palm", 0.01, Z);
  assert.ok(dorsum && dorsum.z < 0);
  assert.ok(palm && palm.z > 0);
});

test("伸展开掌背：甲板朝镜头", () => {
  const fo = computeFingerNailOrientation(
    joints({ x: 0, y: -0.1, z: 0 }, { x: 0, y: -0.1, z: 0 }, { x: 0, y: -0.1, z: 0 }),
    { x: 0, y: 0, z: -1 },
    Z,
  );
  assert.ok(fo);
  assert.ok(fo.curl < 0.05);
  assert.equal(fo.facingCamera, true);
});

test("握拳抓握（中度蜷曲、甲面朝镜头）：先验渲染", () => {
  const fo = computeFingerNailOrientation(
    joints({ x: 0, y: -0.1, z: 0 }, { x: 0, y: -0.05, z: 0.0866 }, { x: 0, y: -0.1, z: 0 }),
    { x: 0, y: 0, z: -1 },
    Z,
  );
  assert.ok(fo);
  assert.ok(fo.curl > 0.6);
  assert.equal(fo.facingCamera, true);
});

test("蜷指钩指（手背朝上镜头、大屈曲）：先验渲染", () => {
  const fo = computeFingerNailOrientation(
    joints({ x: 0, y: 0.1, z: 0 }, { x: 0, y: 0.05, z: 0.0866 }, { x: 0, y: 0.1, z: -0.05 }),
    { x: 0, y: -0.5, z: -0.866 },
    Z,
  );
  assert.ok(fo);
  assert.equal(fo.facingCamera, true);
});

test("掌面伸直指：甲板背向镜头，隐藏", () => {
  const fo = computeFingerNailOrientation(
    joints({ x: 0, y: -0.1, z: 0 }, { x: 0, y: -0.1, z: 0 }, { x: 0, y: -0.1, z: 0 }),
    { x: 0, y: 0, z: 1 },
    Z,
  );
  assert.ok(fo);
  assert.equal(fo.facingCamera, false);
  assert.equal(fo.edgeOn, false);
});

test("掌面回蜷（深度蜷曲、指尖回朝镜头）：先验渲染", () => {
  const fo = computeFingerNailOrientation(
    joints({ x: 0, y: -0.1, z: 0 }, { x: 0, y: -0.05, z: -0.0866 }, { x: 0, y: -0.05, z: 0.0866 }),
    { x: 0, y: 0, z: 1 },
    Z,
  );
  assert.ok(fo);
  assert.ok(fo.curl > 1.5);
  assert.equal(fo.facingCamera, true);
});

test("比耶蜷曲指（约90°侧缘）：edge-on 交佐证信号", () => {
  const fo = computeFingerNailOrientation(
    joints({ x: 0, y: -0.1, z: 0 }, { x: 0, y: 0, z: 0.1 }, { x: 0, y: -0.1, z: 0 }),
    { x: 0, y: 0, z: -1 },
    Z,
  );
  assert.ok(fo);
  assert.equal(fo.facingCamera, false);
  assert.equal(fo.edgeOn, true);
  assert.ok(Math.abs(fo.nailNormal.z) <= NAIL_FACING_COS);
});

test("蜷曲几何分支：横轴垂直远端2D轴、横向投影按朝镜头因子收紧", () => {
  const lm = openHand();
  // 构造蜷曲远端：DIP→TIP 指向画面下方偏右
  lm[NAIL_DIPS[2]] = { x: 0.5, y: 0.4, z: 0 };
  lm[NAIL_TIPS[2]] = { x: 0.54, y: 0.5, z: 0.05 };
  const curled = computeNailGeometry(lm, 2, 1000, 1000, {
    zScale: Z,
    curled: { curl: 1.2, facingFactor: 0.5 },
  });
  assert.ok(curled);
  assert.ok(Math.abs((curled.transverseProjection ?? 1) - 0.5) < 1e-9);
  const plain = computeNailGeometry(lm, 2, 1000, 1000, { zScale: Z });
  assert.ok(plain);
  // 蜷曲分支宽度应窄于未收紧（facingFactor<1）的同输入几何
  assert.ok(curled.width <= plain.width + 1e-6);
});