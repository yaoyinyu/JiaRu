// 选核路径对拍：闭式 RMS 快速路径必须与「逐候选真卷积」参考实现选出同一核宽。
//
// 这是 S6 优化（性能从 P95 4.72ms 降到 ~1.3ms）的正确性保险：快速路径只改「怎么算出
// 每个候选的 RMS」，不改「取最后一个满足界的核宽」这一语义，因此这里独立实现一份
// 参考选核，在随机半径向量上逐例比对 sigma 与 applied；真实数据的一致性由
// nail-texture-radius-smoothing-parity.test.ts 的 16 例指纹对拍兜底。

import assert from "node:assert/strict";
import test from "node:test";
import { computeRadialLattice } from "../src/lib/nail-texture-recognition/radial-field.ts";
import { smoothRadiusVector } from "../src/lib/nail-texture-recognition/radial-smoothing.ts";

const GRID = [0.5, 1, 1.5, 2, 2.5, 3, 4, 5, 6, 8];

/** 确定性伪随机（xorshift32），保证用例可复现。 */
function makeRandom(seed: number): () => number {
  let state = seed >>> 0;
  return () => {
    state ^= state << 13;
    state >>>= 0;
    state ^= state >>> 17;
    state ^= state << 5;
    state >>>= 0;
    return state / 0x100000000;
  };
}

function medianOf(values: Float64Array): number {
  const sorted = Float64Array.from(values).sort();
  const middle = sorted.length >> 1;
  return sorted.length % 2 === 0 ? (sorted[middle - 1] + sorted[middle]) / 2 : sorted[middle];
}

/** 参考实现：某个候选核宽的真实卷积 RMS。 */
function referenceRms(radius: Float64Array, arcPerBin: number, sigma: number): number {
  const length = radius.length;
  const sigmaBins = sigma / arcPerBin;
  if (!(sigmaBins > 0)) return Infinity;
  const half = Math.max(1, Math.ceil(3 * sigmaBins));
  const kernel = new Float64Array(2 * half + 1);
  let total = 0;
  for (let offset = -half; offset <= half; offset += 1) {
    const weight = Math.exp(-0.5 * (offset / sigmaBins) ** 2);
    kernel[offset + half] = weight;
    total += weight;
  }
  for (let index = 0; index < kernel.length; index += 1) kernel[index] /= total;

  let sum = 0;
  for (let index = 0; index < length; index += 1) {
    let accumulator = 0;
    for (let tap = -half; tap <= half; tap += 1) {
      accumulator += radius[(index + tap + length * (half + 1)) % length] * kernel[tap + half];
    }
    sum += (accumulator - radius[index]) ** 2;
  }
  return Math.sqrt(sum / length);
}

/** 参考选核：逐候选真卷积 + 真实 RMS，取最后一个满足界的核宽。 */
function referenceSigma(radius: Float64Array, arcPerBin: number, tau: number): number {
  let sigma = 0;
  for (const candidate of [...GRID].sort((left, right) => left - right)) {
    if (referenceRms(radius, arcPerBin, candidate) <= tau) sigma = candidate;
  }
  return sigma;
}

interface Case {
  name: string;
  length: number;
  baseRadius: number;
  jitter: number;
  tau: number;
}

const CASES: Case[] = [
  { name: "2048 bin 中等抖动", length: 2048, baseRadius: 70, jitter: 0.5, tau: 0.7 },
  { name: "2048 bin 强抖动", length: 2048, baseRadius: 70, jitter: 2.5, tau: 0.7 },
  { name: "2048 bin 几乎无抖动", length: 2048, baseRadius: 70, jitter: 0.05, tau: 0.7 },
  { name: "2048 bin 大半径", length: 2048, baseRadius: 160, jitter: 1.2, tau: 0.5 },
  { name: "2048 bin 小半径", length: 2048, baseRadius: 12, jitter: 0.4, tau: 0.7 },
  { name: "2048 bin τ 极小（不允许任何平滑）", length: 2048, baseRadius: 70, jitter: 0.8, tau: 1e-6 },
  { name: "2048 bin τ 极大（必取最大核宽）", length: 2048, baseRadius: 70, jitter: 0.8, tau: 1e9 },
  { name: "512 bin", length: 512, baseRadius: 60, jitter: 0.6, tau: 0.7 },
  { name: "256 bin", length: 256, baseRadius: 45, jitter: 0.6, tau: 0.7 },
  { name: "64 bin 短向量（触发全扫回退）", length: 64, baseRadius: 1.5, jitter: 0.1, tau: 0.7 },
];

test("fast kernel selection matches the brute-force reference on every case", () => {
  const offenders: string[] = [];
  for (const case_ of CASES) {
    const random = makeRandom(case_.length * 7919 + Math.round(case_.baseRadius * 13) + 1);
    const radius = new Float32Array(case_.length);
    const phase = random() * Math.PI * 2;
    for (let index = 0; index < case_.length; index += 1) {
      const angle = (index / case_.length) * Math.PI * 2;
      // 低阶形状 + 每 bin 高频抖动：贴近真实半径向量的频谱特征。
      const shape = case_.baseRadius * (1 + 0.08 * Math.sin(2 * angle + phase) + 0.04 * Math.cos(3 * angle));
      const noise = (random() - 0.5) * 2 * case_.jitter;
      radius[index] = shape + noise;
    }

    const lattice = computeRadialLattice(64, 64, 31.5, 31.5, case_.length);
    const values = Float64Array.from(radius);
    const arcPerBin = (2 * Math.PI * Math.max(1, medianOf(values))) / values.length;
    const expected = referenceSigma(values, arcPerBin, case_.tau);

    const result = smoothRadiusVector(radius, lattice.bins, lattice.distance, {
      mode: "rms-bounded-gaussian",
      deviationRmsArcPixels: case_.tau,
      gridArcPixels: GRID,
      areaCompensation: true,
    });

    if (result.sigmaArcPixels !== expected) {
      offenders.push(`${case_.name}：快速路径 σ=${result.sigmaArcPixels}，参考 σ=${expected}`);
    }
    if (result.applied !== expected > 0) {
      offenders.push(`${case_.name}：applied=${result.applied} 与参考 σ=${expected} 不一致`);
    }
  }
  assert.equal(offenders.length, 0, offenders.join("\n"));
});

test("threshold sweep: decisions stay exact at the pruning boundary", () => {
  // 闭式 RMS 只用于剪枝，若它在阈值附近判错就会少选/多选一个核宽。这里把 τ 直接
  // 设在每个候选「真实 RMS ±1e-9 / ±1e-8 / ±1e-6」的位置上，逐点比对与参考实现的一致性
  // —— 也就同时把「闭式与真卷积之差 ≤1e-9」变成可验证的事实（模块注释引用此处）。
  const offenders: string[] = [];
  const offsets = [0, 1e-9, -1e-9, 1e-8, -1e-8, 1e-6, -1e-6];

  for (const case_ of CASES) {
    if (case_.length < 256) continue;
    const random = makeRandom(case_.length * 31337 + 11);
    const radius = new Float32Array(case_.length);
    for (let index = 0; index < case_.length; index += 1) {
      const angle = (index / case_.length) * Math.PI * 2;
      radius[index] = case_.baseRadius * (1 + 0.08 * Math.sin(2 * angle)) + (random() - 0.5) * 2 * case_.jitter;
    }
    const values = Float64Array.from(radius);
    const arcPerBin = (2 * Math.PI * Math.max(1, medianOf(values))) / values.length;
    const lattice = computeRadialLattice(64, 64, 31.5, 31.5, case_.length);

    const reference = [...GRID].sort((left, right) => left - right).map((sigma) => ({
      sigma,
      rms: referenceRms(values, arcPerBin, sigma),
    }));

    for (const candidate of reference) {
      for (const offset of offsets) {
        const tau = candidate.rms + offset;
        const expected = reference.reduce((largest, entry) => (entry.rms <= tau ? entry.sigma : largest), 0);
        const result = smoothRadiusVector(radius, lattice.bins, lattice.distance, {
          mode: "rms-bounded-gaussian",
          deviationRmsArcPixels: tau,
          gridArcPixels: GRID,
          areaCompensation: false,
        });
        if (result.sigmaArcPixels !== expected) {
          offenders.push(`${case_.name} τ=${tau.toFixed(12)}：模块 σ=${result.sigmaArcPixels}，参考 σ=${expected}`);
        }
      }
    }
  }
  assert.equal(offenders.length, 0, offenders.slice(0, 10).join("\n"));
});

test("compensation still keeps the decoded area within 0.5% after the fast path", () => {
  const offenders: string[] = [];
  for (const case_ of CASES) {
    if (case_.tau > 1e8) continue;
    const random = makeRandom(case_.length * 104729 + 5);
    const radius = new Float32Array(case_.length);
    for (let index = 0; index < case_.length; index += 1) {
      const angle = (index / case_.length) * Math.PI * 2;
      radius[index] = case_.baseRadius * (1 + 0.08 * Math.sin(2 * angle)) + (random() - 0.5) * 2 * case_.jitter;
    }
    const lattice = computeRadialLattice(96, 96, 47.5, 47.5, case_.length);
    const result = smoothRadiusVector(radius, lattice.bins, lattice.distance, {
      mode: "rms-bounded-gaussian",
      deviationRmsArcPixels: case_.tau,
      gridArcPixels: GRID,
      areaCompensation: true,
    });
    if (!result.applied) continue;

    const areaOf = (values: Float32Array): number => {
      let area = 0;
      for (let index = 0; index < lattice.distance.length; index += 1) {
        const logit = Math.fround(Math.fround(values[lattice.bins[index]]) - lattice.distance[index]);
        if (logit >= 0) area += 1;
      }
      return area;
    };
    const before = areaOf(radius);
    if (before < 200) continue; // 半径 ~1px 的退化用例面积只有个位数，1 像素即 >10%，不具判别力
    const after = areaOf(result.radius);
    const relative = Math.abs(after - before) / Math.max(1, before);
    if (relative > 0.005) offenders.push(`${case_.name}：面积相对变化 ${(relative * 100).toFixed(3)}%`);
  }
  assert.equal(offenders.length, 0, offenders.join("\n"));
});
