/**
 * 原像素径向场的浏览器宿主实现（对齐 model/training/native-pixel-radial-field.py）。
 *
 * 数值口径（与 Python 逐位对齐）：
 * - 坐标与角度在 float64 计算；distance / radius / logits 存储为 float32（Math.fround）。
 * - np.mod(a, 2π) 复刻为 a − floor(a/2π)·2π；np.interp 的环形回绕插值在 double 内
 *   计算后 cast float32；scatter max/min 与比较均按 float32 值进行。
 * - maskLogit = radius[angleBin] − distance，零阈值解码。
 */

/** 默认角度采样数；与服务端 radial_input 及导出图输入一致。 */
export const RADIAL_ANGULAR_SAMPLES = 2048;
/** 径向采样数：offsets −64..64。 */
export const RADIAL_RADIAL_SAMPLES = 129;

export interface RadialLattice {
  /** H×W 的 int32 角度 bin（行主序）。 */
  bins: Int32Array;
  /** H×W 的 float32 原点距离（行主序）。 */
  distance: Float32Array;
}

/** round-half-even：对齐 Python round() 的银行家舍入。 */
export function roundHalfEven(value: number): number {
  const floor = Math.floor(value);
  const fraction = value - floor;
  if (fraction > 0.5) return floor + 1;
  if (fraction < 0.5) return floor;
  return floor % 2 === 0 ? floor : floor + 1;
}

/**
 * 以 (centerX, centerY) 为原点生成整幅网格的角度 bin 与距离。
 * 对齐 lattice(shape, center, angular_samples)。
 */
export function computeRadialLattice(
  width: number,
  height: number,
  centerX: number,
  centerY: number,
  angularSamples: number = RADIAL_ANGULAR_SAMPLES
): RadialLattice {
  if (!Number.isFinite(centerX) || !Number.isFinite(centerY)) {
    throw new Error("radial_center_not_finite");
  }
  if (!Number.isInteger(angularSamples) || angularSamples < 16) {
    throw new Error("radial_angular_samples_invalid");
  }
  const bins = new Int32Array(width * height);
  const distance = new Float32Array(width * height);
  const twoPi = 2 * Math.PI;
  const angularScale = angularSamples / twoPi;
  for (let y = 0; y < height; y++) {
    const rowOffset = y * width;
    const dy = y - centerY;
    for (let x = 0; x < width; x++) {
      const dx = x - centerX;
      const angle = Math.atan2(dy, dx);
      const wrapped = angle - Math.floor(angle / twoPi) * twoPi;
      let bin = Math.floor(wrapped * angularScale);
      if (bin > angularSamples - 1) bin = angularSamples - 1;
      bins[rowOffset + x] = bin;
      distance[rowOffset + x] = Math.fround(Math.hypot(dx, dy));
    }
  }
  return { bins, distance };
}

/**
 * 由完整二值粗 mask 拟合每角度半径：最外正像素与其外第一个背景像素的中点。
 * 对齐 fit_radius(mask, bins, distance, angular_samples)；空 mask 返回 null。
 */
export function fitRadialRadius(
  mask: Uint8Array,
  bins: Int32Array,
  distance: Float32Array,
  width: number,
  height: number,
  angularSamples: number = RADIAL_ANGULAR_SAMPLES
): Float32Array | null {
  if (mask.length !== bins.length || mask.length !== distance.length) {
    throw new Error("radial_field_shape_mismatch");
  }
  const positive = new Float32Array(angularSamples).fill(Number.NEGATIVE_INFINITY);
  let hasForeground = false;
  for (let index = 0; index < mask.length; index++) {
    if (mask[index] === 0) continue;
    hasForeground = true;
    const bin = bins[index];
    const value = distance[index];
    if (value > positive[bin]) positive[bin] = value;
  }
  if (!hasForeground) return null;

  let resolved = positive;
  const known: number[] = [];
  for (let bin = 0; bin < angularSamples; bin++) {
    if (Number.isFinite(positive[bin])) known.push(bin);
  }
  if (known.length < angularSamples) {
    // np.interp(all_bins, [known-N, known, known+N], tile(positive[known], 3))，
    // double 内插值后 cast float32；tiled xp 严格递增且覆盖全部查询点。
    const interpolated = new Float32Array(angularSamples);
    const segment = known.length;
    for (let bin = 0; bin < angularSamples; bin++) {
      const query = bin;
      // 在 tiled xp 中定位：中段 [0, segment) 直接映射，避免拼接 N 长数组。
      let lo = 0;
      let hi = segment * 3 - 1;
      const xpAt = (index: number): number => {
        const wrapped = ((index % segment) + segment) % segment;
        const cycle = Math.floor(index / segment);
        return known[wrapped] + (cycle - 1) * angularSamples;
      };
      const fpAt = (index: number): number => positive[known[((index % segment) + segment) % segment]];
      if (query <= xpAt(0)) {
        interpolated[bin] = fpAt(0);
      } else if (query >= xpAt(segment * 3 - 1)) {
        interpolated[bin] = fpAt(segment * 3 - 1);
      } else {
        while (hi - lo > 1) {
          const mid = (lo + hi) >> 1;
          if (xpAt(mid) <= query) lo = mid;
          else hi = mid;
        }
        const x0 = xpAt(lo);
        const x1 = xpAt(hi);
        const y0 = fpAt(lo);
        const y1 = fpAt(hi);
        const slope = (y1 - y0) / (x1 - x0);
        interpolated[bin] = Math.fround(slope * (query - x0) + y0);
      }
    }
    resolved = interpolated;
  }

  const nextBackground = new Float32Array(angularSamples).fill(Number.POSITIVE_INFINITY);
  for (let index = 0; index < mask.length; index++) {
    if (mask[index] !== 0) continue;
    const bin = bins[index];
    const value = distance[index];
    if (value > resolved[bin] && value < nextBackground[bin]) nextBackground[bin] = value;
  }

  const radius = new Float32Array(angularSamples);
  for (let bin = 0; bin < angularSamples; bin++) {
    const inner = resolved[bin];
    const outer = Number.isFinite(nextBackground[bin])
      ? nextBackground[bin]
      : Math.fround(inner + 1);
    radius[bin] = Math.fround(inner + Math.fround((outer - inner) * Math.fround(0.5)));
  }
  return radius;
}

/**
 * 零阈值解码：radius[angleBin] − distance（float32 减法）。
 * 对齐 logits(radius, bins, distance)。
 */
export function radialMaskLogits(
  radius: Float32Array,
  bins: Int32Array,
  distance: Float32Array
): Float32Array {
  if (bins.length !== distance.length) {
    throw new Error("radial_logits_shape_mismatch");
  }
  const logits = new Float32Array(bins.length);
  for (let index = 0; index < bins.length; index++) {
    logits[index] = Math.fround(radius[bins[index]] - distance[index]);
  }
  return logits;
}

/**
 * square_context_035 ROI：1.7 倍整边正方形，中心 clamp 于图内。
 * 对齐 analyze-saved-nail-roi-coverage.crop_box（round 为银行家舍入）。
 */
export function cropSquareContext035(
  box: { x0: number; y0: number; x1: number; y1: number },
  width: number,
  height: number
): { left: number; top: number; side: number } | null {
  if (
    !Number.isFinite(box.x0) || !Number.isFinite(box.y0) ||
    !Number.isFinite(box.x1) || !Number.isFinite(box.y1) ||
    box.x1 <= box.x0 || box.y1 <= box.y0
  ) {
    throw new Error("invalid_candidate_box");
  }
  const side = Math.max(16, Math.ceil(Math.max(box.x1 - box.x0, box.y1 - box.y0) * 1.7));
  if (side > Math.min(width, height)) return null;
  const left = Math.min(Math.max(roundHalfEven((box.x0 + box.x1) / 2 - side / 2), 0), width - side);
  const top = Math.min(Math.max(roundHalfEven((box.y0 + box.y1) / 2 - side / 2), 0), height - side);
  return { left, top, side };
}
