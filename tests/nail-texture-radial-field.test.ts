import assert from "node:assert/strict";
import test from "node:test";
import {
  computeRadialLattice,
  cropSquareContext035,
  fitRadialRadius,
  radialMaskLogits,
  roundHalfEven,
} from "../src/lib/nail-texture-recognition/radial-field.ts";

test("roundHalfEven uses banker's rounding at .5 ties", () => {
  assert.equal(roundHalfEven(0.5), 0);
  assert.equal(roundHalfEven(1.5), 2);
  assert.equal(roundHalfEven(2.5), 2);
  assert.equal(roundHalfEven(-1.5), -2);
  assert.equal(roundHalfEven(0.4), 0);
  assert.equal(roundHalfEven(0.6), 1);
  // -0.5 的平局同样落到偶数 0。JS 实现返回 +0（Object.is(result, -0) 为 false），
  // 数值口径与 Python round(-0.5) === 0 一致；assert.equal 对 ±0 均成立。
  assert.equal(roundHalfEven(-0.5), 0);
});

test("cropSquareContext035 sizes, banker-rounds and clamps the square context crop", () => {
  // 最小边 16：小框也放大到 16×16，中心落在图外时钳到 0。
  assert.deepEqual(cropSquareContext035({ x0: 5, y0: 5, x1: 6, y1: 6 }, 32, 32), {
    left: 0,
    top: 0,
    side: 16,
  });

  // 1.7 倍向上取整：框宽 10 → side = ceil(10·1.7) = 17；
  // 中心 32 → left/top = roundHalfEven(32 − 8.5) = roundHalfEven(23.5) = 24（23 奇数进位）。
  assert.deepEqual(cropSquareContext035({ x0: 27, y0: 30, x1: 37, y1: 34 }, 64, 64), {
    left: 24,
    top: 24,
    side: 17,
  });

  // 中心舍入为银行家舍入：中心 33 → 24.5 → 24（24 偶数舍去；四舍五入会给 25）。
  assert.deepEqual(cropSquareContext035({ x0: 28, y0: 30, x1: 38, y1: 34 }, 64, 64), {
    left: 24,
    top: 24,
    side: 17,
  });

  // clamp 到 [0, width − side]：中心 28、side 16 → 原始 left 20 被钳到 16；top = 4 不受影响。
  assert.deepEqual(cropSquareContext035({ x0: 26, y0: 10, x1: 30, y1: 14 }, 32, 32), {
    left: 16,
    top: 4,
    side: 16,
  });
  // 左侧越界（roundHalfEven(−5.5) = −6）钳到 0。
  assert.deepEqual(cropSquareContext035({ x0: 1, y0: 10, x1: 4, y1: 14 }, 32, 32), {
    left: 0,
    top: 4,
    side: 16,
  });

  // side 超过图短边时无法放置 → null。
  assert.equal(cropSquareContext035({ x0: 0, y0: 0, x1: 19, y1: 5 }, 20, 20), null);

  // 非法框（x1 <= x0 或 y1 <= y0）直接抛错。
  assert.throws(() => cropSquareContext035({ x0: 5, y0: 5, x1: 5, y1: 8 }, 32, 32), /invalid_candidate_box/);
  assert.throws(() => cropSquareContext035({ x0: 5, y0: 8, x1: 9, y1: 8 }, 32, 32), /invalid_candidate_box/);
});

test("computeRadialLattice stores float32 distances and angle bins within range", () => {
  const width = 36;
  const height = 36;
  const centerX = 17.3;
  const centerY = 18.7;
  const angularSamples = 32;
  const lattice = computeRadialLattice(width, height, centerX, centerY, angularSamples);

  assert.equal(lattice.bins.length, width * height);
  assert.equal(lattice.distance.length, width * height);
  let outOfRange = 0;
  for (let index = 0; index < lattice.bins.length; index++) {
    const bin = lattice.bins[index];
    if (!Number.isInteger(bin) || bin < 0 || bin > angularSamples - 1) outOfRange += 1;
  }
  assert.equal(outOfRange, 0, "all angle bins stay within [0, angularSamples - 1]");

  // 距离按 float32 存储：与 double 计算后 fround 的值逐位一致。
  assert.equal(lattice.distance[0], Math.fround(Math.hypot(0 - centerX, 0 - centerY)));

  // 距中心 (17.3, 18.7) 最近的像素是 (17, 19)，距离 hypot(0.3, 0.3) ≈ 0.4243 为全场最小。
  const nearestIndex = 19 * width + 17;
  assert.equal(lattice.distance[nearestIndex], Math.fround(Math.hypot(17 - centerX, 19 - centerY)));
  let minIndex = 0;
  for (let index = 1; index < lattice.distance.length; index++) {
    if (lattice.distance[index] < lattice.distance[minIndex]) minIndex = index;
  }
  assert.equal(minIndex, nearestIndex);
  assert.ok(lattice.distance[nearestIndex] < 0.43);

  // 对角对称抽查：(17,17) 与 (19,19) 相对中心的 |dx|/|dy| 互换，距离应几乎一致。
  const diagonalA = lattice.distance[17 * width + 17];
  const diagonalB = lattice.distance[19 * width + 19];
  assert.ok(Math.abs(diagonalA - diagonalB) < 1e-12);
});

test("fitRadialRadius takes the midpoint between outermost foreground and next background", () => {
  // 1×4 合成场：bin0 前景最远 dist=1、其外第一个背景 dist=2 → (1+2)/2 = 1.5；
  // bin1 前景最远 dist=3、背景 dist=4 → 3.5。无空 bin，全为 float32 精确值。
  const radius = fitRadialRadius(
    Uint8Array.from([1, 0, 1, 0]),
    Int32Array.from([0, 0, 1, 1]),
    Float32Array.from([1, 2, 3, 4]),
    4,
    1,
    2
  );
  assert.deepEqual(Array.from(radius as Float32Array), [1.5, 3.5]);
});

test("fitRadialRadius interpolates empty angle bins to finite radii", () => {
  // bin1 无前景：known=[0,2]，环形回绕插值（xp=[-3,-1,0,2,3,5]）把 resolved 补成 [1,2,3]；
  // bin1 唯一背景像素 dist=2 不大于 resolved → 外推 inner+1=3 → 半径 2.5，全部有限。
  const radius = fitRadialRadius(
    Uint8Array.from([1, 0, 1]),
    Int32Array.from([0, 1, 2]),
    Float32Array.from([1, 2, 3]),
    3,
    1,
    3
  );
  assert.ok(radius);
  for (const value of radius) {
    assert.ok(Number.isFinite(value));
  }
  assert.deepEqual(Array.from(radius), [1.5, 2.5, 3.5]);
});

test("fitRadialRadius returns null for an empty mask", () => {
  assert.equal(
    fitRadialRadius(
      new Uint8Array(4),
      Int32Array.from([0, 0, 1, 1]),
      Float32Array.from([1, 2, 3, 4]),
      4,
      1,
      2
    ),
    null
  );
});

test("radialMaskLogits decodes radius[bins] - distance per element in float32", () => {
  const logits = radialMaskLogits(
    Float32Array.from([1.5, 2.5, 3.5]),
    Int32Array.from([0, 1, 2, 2, 1]),
    Float32Array.from([1, 2, 3, 1, 4])
  );
  // 逐元素公式 radius[bins[i]] − distance[i]（float32 减法）。
  assert.deepEqual(Array.from(logits), [0.5, 0.5, 0.5, 2.5, -1.5]);

  assert.throws(
    () => radialMaskLogits(Float32Array.from([1]), Int32Array.from([0, 0]), Float32Array.from([1])),
    /radial_logits_shape_mismatch/
  );
});

test("radial field pipeline fits finite radii and decodes foreground sign on a 4x4 lattice", () => {
  const lattice = computeRadialLattice(4, 4, 1.5, 1.5, 16);
  const mask = new Uint8Array(16);
  for (let index = 0; index < mask.length; index++) {
    mask[index] = lattice.distance[index] <= 2.1 ? 1 : 0;
  }

  const radius = fitRadialRadius(mask, lattice.bins, lattice.distance, 4, 4, 16);
  assert.ok(radius);
  for (const value of radius) {
    assert.ok(Number.isFinite(value));
  }

  const logits = radialMaskLogits(radius, lattice.bins, lattice.distance);
  for (let index = 0; index < logits.length; index++) {
    // 前景解码为非负、背景为负。
    assert.equal(logits[index] >= 0, mask[index] === 1);
    // 逐元素公式复核：logits[i] === fround(radius[bins[i]] − distance[i])。
    assert.equal(
      logits[index],
      Math.fround(radius[lattice.bins[index]] - lattice.distance[index])
    );
  }
});
