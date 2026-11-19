/**
 * 半径向量平滑：RMS 有界循环高斯 + 面积补偿（2026-11-17 循环093 零推理证据）。
 *
 * 背景：模型 Stage B 的半径头在 2048 个角度 bin 上逐点独立回归，相邻 bin 之间
 * 存在约 1px 的高频抖动。沿角度做循环低通可把训练域严格联合从 248/634 提到
 * 420/634，且区域精度与边缘 F1 同向改善（见
 * model/reports/cycle093-bias-neutral-smoothing-v1/report.json）。
 *
 * 本模块只做纯计算，不读写任何全局状态，缺省不启用（mode 未声明时调用方应
 * 直接使用原半径向量，输出与旧版本逐位一致）。
 */

export interface RadiusSmoothingOptions {
  mode: "none" | "rms-bounded-gaussian";
  /** 允许的 RMS 半径偏移（弧长像素）。取满足该界的大型核宽。 */
  deviationRmsArcPixels: number;
  /** 候选核宽（弧长像素），升序。 */
  gridArcPixels: readonly number[];
  /** 是否做面积补偿，使平滑本身不改变 mask 面积。 */
  areaCompensation: boolean;
}

export interface RadiusSmoothingResult {
  radius: Float32Array;
  sigmaArcPixels: number;
  /** 面积补偿施加的整体半径平移（像素）；未补偿为 0。 */
  areaCompensationPixels: number;
  /** 补偿后剩余面积误差（像素数），仅诊断。 */
  areaResidualPixels: number;
  applied: boolean;
}

/** 闭式 RMS 与真实卷积的差在 1e-13 量级；阈值附近按此带宽触发真卷积复核。 */
const CRITICAL_MARGIN = 1e-6;

const DEFAULT_OPTIONS: RadiusSmoothingOptions = {
  mode: "none",
  deviationRmsArcPixels: 0.7,
  gridArcPixels: [0.5, 1, 1.5, 2, 2.5, 3, 4, 5, 6, 8],
  areaCompensation: true,
};

function gaussianKernel(sigmaBins: number): Float64Array | null {
  if (!(sigmaBins > 0) || !Number.isFinite(sigmaBins)) return null;
  const half = Math.max(1, Math.ceil(3 * sigmaBins));
  const kernel = new Float64Array(2 * half + 1);
  let total = 0;
  for (let offset = -half; offset <= half; offset += 1) {
    const weight = Math.exp(-0.5 * (offset / sigmaBins) ** 2);
    kernel[offset + half] = weight;
    total += weight;
  }
  if (!(total > 0)) return null;
  for (let index = 0; index < kernel.length; index += 1) kernel[index] /= total;
  return kernel;
}

function circularConvolve(values: Float64Array, kernel: Float64Array): Float64Array {
  const length = values.length;
  const half = (kernel.length - 1) / 2;
  const output = new Float64Array(length);
  for (let index = 0; index < length; index += 1) {
    let accumulator = 0;
    for (let tap = -half; tap <= half; tap += 1) {
      const source = (index + tap + length * (half + 1)) % length;
      accumulator += values[source] * kernel[tap + half];
    }
    output[index] = accumulator;
  }
  return output;
}

/** 循环自相关 C(m) = mean_i r[i]·r[i+m]，m ∈ [0, maxLag]；返回按 (lag + maxLag) 索引的对称数组。 */
function circularAutocorrelation(values: Float64Array, maxLag: number): Float64Array {
  const length = values.length;
  const lags = new Float64Array(2 * maxLag + 1);
  for (let lag = 0; lag <= maxLag; lag += 1) {
    let total = 0;
    for (let index = 0; index < length; index += 1) {
      total += values[index] * values[(index + lag) % length];
    }
    const mean = total / length;
    lags[maxLag + lag] = mean;
    if (lag > 0) lags[maxLag - lag] = mean;
  }
  return lags;
}

/**
 * 闭式 RMS：RMS² = ΣΣ h_k h_l·C(k−l) − 2Σ h_k·C(k) + C(0)。
 *
 * 展开自 mean_i(Σ_k h_k(r[i+k]−r[i]))²，用循环自相关一次代替每核一次卷积；
 * 用于「网格选核」阶段把 O(网格数 × bins × 核长) 降到 O(bins × 最大核长 + 网格数 × 核长²)。
 * 与真实卷积的差在 1e-13 量级（C(0)≈r²≈10⁴ 相减去凑 RMS²≈0.5 的抵消），
 * 因此临界处必须用真实卷积复核，见 `smoothRadiusVector` 的复核分支。
 */
function closedFormRms(autocorrelation: Float64Array, half: number, kernel: Float64Array): number {
  const maxLag = (autocorrelation.length - 1) / 2;
  const middle = maxLag;
  let quadratic = 0;
  for (let left = -half; left <= half; left += 1) {
    const weightLeft = kernel[left + half];
    for (let right = -half; right <= half; right += 1) {
      quadratic += weightLeft * kernel[right + half] * autocorrelation[middle + left - right];
    }
  }
  let linear = 0;
  for (let offset = -half; offset <= half; offset += 1) {
    linear += kernel[offset + half] * autocorrelation[middle + offset];
  }
  const variance = quadratic - 2 * linear + autocorrelation[middle];
  return variance <= 0 ? 0 : Math.sqrt(variance);
}

/** 参考实现：逐个候选真卷积，取最后一个满足 RMS 界的核宽（语义基准，仅慢路径与对拍使用）。 */
function fullScanSelection(
  original: Float64Array,
  candidates: { sigma: number; kernel: Float64Array }[],
  deviationRms: number
): { sigma: number; smoothed: Float64Array | null } {
  let smoothed: Float64Array | null = null;
  let sigma = 0;
  for (const candidate of candidates) {
    const vector = circularConvolve(original, candidate.kernel);
    if (rmsDelta(vector, original) <= deviationRms) {
      smoothed = vector;
      sigma = candidate.sigma;
    }
  }
  return { sigma, smoothed };
}

/**
 * 选核：**降序找第一个真实卷积满足 RMS 界的核宽**（等价于「取满足界的最大核宽」，
 * 不需要单调性假设）。闭式 RMS 只用来**跳过**明显不通过的候选；任何一个候选只要
 * 有通过的可能，就必须用真实卷积裁决，因此最终结果与全扫参考逐位同值。
 *
 * 质量前提是可验证的数值事实：闭式 RMS 与真实卷积之差 ≤ 1e-9（远小于 CRITICAL_MARGIN
 * 的 1e-6），由 tests/nail-texture-radius-smoothing-selection.test.ts 断言，不靠推断。
 */
function chooseSigma(
  original: Float64Array,
  candidates: { sigma: number; kernel: Float64Array }[],
  deviationRms: number
): { sigma: number; smoothed: Float64Array | null } {
  if (candidates.length === 0) return { sigma: 0, smoothed: null };
  const largestHalf = candidates.reduce((largest, entry) => Math.max(largest, (entry.kernel.length - 1) / 2), 0);
  const maxLag = Math.min(Math.floor(original.length / 2), 2 * largestHalf);
  // 向量过短时近邻 lag 会绕圈，闭式前提不成立，直接走参考实现。
  if (2 * largestHalf > maxLag) return fullScanSelection(original, candidates, deviationRms);

  const autocorrelation = circularAutocorrelation(original, maxLag);
  for (let index = candidates.length - 1; index >= 0; index -= 1) {
    const candidate = candidates[index];
    const estimate = closedFormRms(autocorrelation, (candidate.kernel.length - 1) / 2, candidate.kernel);
    if (estimate > deviationRms + CRITICAL_MARGIN) continue;
    const smoothed = circularConvolve(original, candidate.kernel);
    if (rmsDelta(smoothed, original) <= deviationRms) return { sigma: candidate.sigma, smoothed };
  }
  return { sigma: 0, smoothed: null };
}

function medianOf(values: Float64Array): number {
  const sorted = Float64Array.from(values).sort();
  const middle = sorted.length >> 1;
  if (sorted.length % 2 === 0) return (sorted[middle - 1] + sorted[middle]) / 2;
  return sorted[middle];
}

function perimeterOf(radius: Float64Array, arcPerBin: number): number {
  const length = radius.length;
  let perimeter = 0;
  for (let index = 0; index < length; index += 1) {
    const delta = radius[(index + 1) % length] - radius[index];
    perimeter += Math.hypot(arcPerBin, delta);
  }
  return perimeter;
}

/** 与 radialMaskLogits 同口径的面积：radius[bins] − distance ≥ 0 的像素数。 */
function decodedArea(radius: Float64Array, bins: Int32Array, distance: Float32Array): number {
  let area = 0;
  for (let index = 0; index < distance.length; index += 1) {
    const bin = bins[index];
    if (Math.fround(Math.fround(radius[bin]) - distance[index]) >= 0) area += 1;
  }
  return area;
}

function rmsDelta(left: Float64Array, right: Float64Array): number {
  let total = 0;
  for (let index = 0; index < left.length; index += 1) total += (left[index] - right[index]) ** 2;
  return Math.sqrt(total / Math.max(1, left.length));
}

/**
 * 对半径向量做 RMS 有界循环高斯平滑，并可选做面积补偿。
 *
 * - `mode === "none"`：原样返回，`applied` 为 false（调用方保持旧行为）。
 * - 核宽按弧长给出，通过 `arcPerBin = 2π·medianRadius/bins` 换算为 bin，避免大小甲面尺度不同。
 * - 面积补偿只平移整体半径，不改变形状；`|δ| > 2px` 视为不可信，放弃补偿并保留 `applied`。
 */
export function smoothRadiusVector(
  radius: Float32Array,
  bins: Int32Array,
  distance: Float32Array,
  options: Partial<RadiusSmoothingOptions> = {}
): RadiusSmoothingResult {
  const settings: RadiusSmoothingOptions = { ...DEFAULT_OPTIONS, ...options };
  const unchanged: RadiusSmoothingResult = {
    radius,
    sigmaArcPixels: 0,
    areaCompensationPixels: 0,
    areaResidualPixels: 0,
    applied: false,
  };
  if (settings.mode !== "rms-bounded-gaussian" || radius.length < 8) return unchanged;
  if (bins.length !== distance.length) return unchanged;

  const original = Float64Array.from(radius);
  const medianRadius = medianOf(original);
  const arcPerBin = (2 * Math.PI * Math.max(1, medianRadius)) / original.length;
  if (!(arcPerBin > 0)) return unchanged;

  const candidates: { sigma: number; kernel: Float64Array }[] = [];
  for (const sigma of [...settings.gridArcPixels].sort((left, right) => left - right)) {
    const kernel = gaussianKernel(sigma / arcPerBin);
    if (kernel) candidates.push({ sigma, kernel });
  }

  const selection = chooseSigma(original, candidates, settings.deviationRmsArcPixels);
  if (selection.smoothed === null) return unchanged;
  const chosen = selection.smoothed;
  const chosenSigma = selection.sigma;

  let compensated = chosen;
  let compensation = 0;
  let residual = 0;
  if (settings.areaCompensation) {
    const targetArea = decodedArea(original, bins, distance);
    const currentArea = decodedArea(chosen, bins, distance);
    const perimeter = perimeterOf(chosen, arcPerBin);
    const delta = (targetArea - currentArea) / Math.max(1, perimeter);
    if (Number.isFinite(delta) && Math.abs(delta) <= 2) {
      const shifted = Float64Array.from(chosen, (value) => value + delta);
      const remaining = (targetArea - decodedArea(shifted, bins, distance)) / Math.max(1, perimeter);
      const corrected = Number.isFinite(remaining) && Math.abs(remaining) <= 2
        ? Float64Array.from(shifted, (value) => value + remaining)
        : shifted;
      compensated = corrected;
      compensation = delta + (corrected === shifted ? 0 : remaining);
    } else {
      compensated = chosen;
      compensation = 0;
    }
    residual = decodedArea(compensated, bins, distance) - decodedArea(original, bins, distance);
  }

  return {
    radius: Float32Array.from(compensated, (value) => Math.fround(value)),
    sigmaArcPixels: chosenSigma,
    areaCompensationPixels: Math.fround(compensation),
    areaResidualPixels: residual,
    applied: true,
  };
}
