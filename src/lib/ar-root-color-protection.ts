/** AR 甲根颜色保护（quality-first-v7）：精确面积采样 + 1–2px 平滑内缩保护。 */

export const AR_ROOT_COLOR_PROTECTION_VERSION = "quality-first-v7";

/** 构建期回退开关：默认启用 V7，`NEXT_PUBLIC_AR_ROOT_COLOR_PROTECTION=off` 回到现行采样。 */
export const AR_ROOT_COLOR_PROTECTION_ENABLED =
  process.env.NEXT_PUBLIC_AR_ROOT_COLOR_PROTECTION?.trim().toLowerCase() !== "off";

export interface Affine2D {
  a: number;
  b: number;
  c: number;
  d: number;
  e: number;
  f: number;
}

export interface SourceBounds {
  minX: number;
  minY: number;
  maxX: number;
  maxY: number;
}

export interface TextureAreaIntegral {
  data: Uint32Array;
  width: number;
  height: number;
  pitch: number;
  originX: number;
  originY: number;
  bytes: number;
}

export type RgbSource = Uint8Array | Uint8ClampedArray;
export type PlaneData = { width: number; height: number; data: Uint8ClampedArray };

function clamp01(value: number): number {
  if (!Number.isFinite(value)) return 0;
  return Math.max(0, Math.min(1, value));
}

/** 先应用 right，再应用 left。 */
export function multiplyAffine(left: Affine2D, right: Affine2D): Affine2D {
  return {
    a: left.a * right.a + left.c * right.b,
    b: left.b * right.a + left.d * right.b,
    c: left.a * right.c + left.c * right.d,
    d: left.b * right.c + left.d * right.d,
    e: left.a * right.e + left.c * right.f + left.e,
    f: left.b * right.e + left.d * right.f + left.f,
  };
}

export function invertAffine(matrix: Affine2D): Affine2D | null {
  const det = matrix.a * matrix.d - matrix.b * matrix.c;
  if (!Number.isFinite(det) || det === 0) return null;
  const invDet = 1 / det;
  return {
    a: matrix.d * invDet,
    b: -matrix.b * invDet,
    c: -matrix.c * invDet,
    d: matrix.a * invDet,
    e: (matrix.c * matrix.f - matrix.d * matrix.e) * invDet,
    f: (matrix.b * matrix.e - matrix.a * matrix.f) * invDet,
  };
}

/** 离屏层左上像素坐标 → 原纹理像素坐标；与 textureDrawRect 的绘制矩形一一对应。 */
export function textureLayerToSourceMatrix(
  rect: { x: number; y: number; width: number; height: number },
  textureWidth: number,
  textureHeight: number,
  layerWidth: number,
  layerHeight: number,
): Affine2D | null {
  if (
    textureWidth <= 0 || textureHeight <= 0 || layerWidth <= 0 || layerHeight <= 0 ||
    !(rect.width > 0) || !(rect.height > 0) ||
    !Number.isFinite(rect.x) || !Number.isFinite(rect.y)
  ) return null;
  const scaleX = textureWidth / rect.width;
  const scaleY = textureHeight / rect.height;
  if (!Number.isFinite(scaleX) || !Number.isFinite(scaleY) || scaleX === 0 || scaleY === 0) return null;
  return {
    a: scaleX,
    b: 0,
    c: 0,
    d: scaleY,
    e: -(layerWidth / 2 + rect.x) * scaleX,
    f: -(layerHeight / 2 + rect.y) * scaleY,
  };
}

/** 离屏层左上像素坐标 → 屏幕坐标；生产主画布为 1:1 CSS backing。 */
export function textureLayerToScreenMatrix(
  geometryMatrix: Affine2D,
  layerWidth: number,
  layerHeight: number,
): Affine2D {
  return multiplyAffine(geometryMatrix, {
    a: 1, b: 0, c: 0, d: 1,
    e: -layerWidth / 2,
    f: -layerHeight / 2,
  });
}

/** 离屏层像素 → 设备物理像素。 */
export function textureLayerToPhysicalMatrix(
  geometryMatrix: Affine2D,
  layerWidth: number,
  layerHeight: number,
  devicePixelRatio: number,
): Affine2D | null {
  const ratio = Number.isFinite(devicePixelRatio) && devicePixelRatio > 0 ? devicePixelRatio : 1;
  return multiplyAffine(
    { a: ratio, b: 0, c: 0, d: ratio, e: 0, f: 0 },
    textureLayerToScreenMatrix(geometryMatrix, layerWidth, layerHeight),
  );
}

/** 行积分保留原 8 位 RGB；每个源像素行的最大宽度受 Uint32 精度保护。 */
export function buildTextureAreaIntegral(
  rgb: RgbSource,
  sourceWidth: number,
  sourceHeight: number,
  bounds: SourceBounds,
): TextureAreaIntegral {
  if (
    sourceWidth <= 0 || sourceHeight <= 0 ||
    rgb.length !== sourceWidth * sourceHeight * 3 ||
    !Number.isFinite(bounds.minX) || !Number.isFinite(bounds.minY) ||
    !Number.isFinite(bounds.maxX) || !Number.isFinite(bounds.maxY)
  ) throw new Error("area_integral_input_invalid");
  const originX = Math.max(0, Math.floor(bounds.minX - 16));
  const originY = Math.max(0, Math.floor(bounds.minY - 16));
  const width = Math.min(sourceWidth, Math.ceil(bounds.maxX + 17)) - originX;
  const height = Math.min(sourceHeight, Math.ceil(bounds.maxY + 17)) - originY;
  if (width <= 0 || height <= 0) throw new Error("area_integral_bounds_invalid");
  if (width > 4096) throw new Error("row_integrals_exceed_exact_uint32_capacity");
  const pitch = width + 1;
  const data = new Uint32Array(6 * pitch * height);
  for (let y = 0; y < height; y++) {
    const rowStart = (originY + y) * sourceWidth + originX;
    for (let x = 0; x < width; x++) {
      const j = 3 * (rowStart + x);
      const p = 6 * (y * pitch + x);
      const q = p + 6;
      for (let c = 0; c < 3; c++) {
        const value = rgb[j + c];
        data[q + c] = data[p + c] + value;
        data[q + 3 + c] = data[p + 3 + c] + 2 * data[p + c] + value;
      }
    }
  }
  return { data, width, height, pitch, originX, originY, bytes: data.byteLength };
}

/** 对一个显示像素的四边形做精确面积加权采样；返回复用的 RGB 数组。 */
export function createExactAreaSampler(
  integral: TextureAreaIntegral,
  matrix: Affine2D,
): (x: number, y: number) => Float64Array {
  const { data, width, height, pitch, originX, originY } = integral;
  const det = matrix.a * matrix.d - matrix.b * matrix.c;
  if (!Number.isFinite(det) || det === 0) throw new Error("area_sampler_non_invertible_matrix");
  const ax = matrix.a, ay = matrix.b, bx = matrix.c, by = matrix.d;
  const vx = [0, ax, ax + bx, bx, 0];
  const vy = [0, ay, ay + by, by, 0];
  const rgb = new Float64Array(3);
  const xRel = matrix.e - originX;
  const yRel = matrix.f - originY;
  const inv = 1 / det;
  return (x: number, y: number) => {
    const cx = ax * x + bx * y + xRel;
    const cy = ay * x + by * y + yRel;
    const minX = Math.floor(cx + Math.min(0, ax) + Math.min(0, bx));
    rgb[0] = rgb[1] = rgb[2] = 0;
    if (minX < 0 || minX >= width) throw new Error("row_reference_outside_area_integral");
    for (let edge = 0; edge < 4; edge++) {
      const y0 = cy + vy[edge], y1 = cy + vy[edge + 1];
      const dy = y1 - y0;
      if (dy === 0) continue;
      const x0 = cx + vx[edge], x1 = cx + vx[edge + 1];
      const slope = (x1 - x0) / dy;
      const lo = Math.min(y0, y1), hi = Math.max(y0, y1);
      for (let row = Math.floor(lo); row < Math.ceil(hi); row++) {
        const start = Math.max(lo, row), end = Math.min(hi, row + 1);
        const xa = x0 + (start - y0) * slope, xb = x0 + (end - y0) * slope;
        const left = Math.min(xa, xb), right = Math.max(xa, xb), dx = right - left;
        const ix = Math.floor(left), jx = Math.floor(right);
        if (row < 0 || row >= height || ix < 0 || jx > width) {
          throw new Error("row_color_integration_outside_area_integral");
        }
        const i = 6 * (row * pitch + ix);
        const j = 6 * (row * pitch + jx);
        const ref = 6 * (row * pitch + minX);
        const a = left - ix, b = right - jx;
        const weight = (dy < 0 ? start - end : end - start) * inv;
        if (ix === jx) {
          if (ix === width) {
            for (let c = 0; c < 3; c++) rgb[c] += weight * (data[i + c] - data[ref + c]);
          } else {
            const offset = (a + b) * 0.5;
            for (let c = 0; c < 3; c++) {
              rgb[c] += weight * (data[i + c] - data[ref + c] + offset * (data[i + 6 + c] - data[i + c]));
            }
          }
          continue;
        }
        const l = (1 - a) / dx, r = b / dx, lc = (1 + a) * 0.5 * l, rc = 0.5 * b * r;
        const span = jx - ix - 1;
        const middleWeight = 1 / (2 * dx);
        for (let c = 0; c < 3; c++) {
          const base = data[ref + c], leftF = data[i + c], nextF = data[i + 6 + c], rightF = data[j + c];
          const middle = span
            ? (data[j + 3 + c] - data[i + 9 + c] - 2 * span * base) * middleWeight
            : 0;
          const leftAvg = l * (leftF - base) + lc * (nextF - leftF);
          const rightAvg = r * (rightF - base) + (jx === width ? 0 : rc * (data[j + 6 + c] - rightF));
          rgb[c] += weight * (middle + leftAvg + rightAvg);
        }
      }
    }
    return rgb;
  };
}

/** 方形不透明内缩：邻域半径 1 为 1px，半径 2 为 2px。输出只包含 alpha。 */
export function buildSquareOpacityMask(
  rgba: Uint8ClampedArray | Uint8Array,
  width: number,
  height: number,
  radius: 1 | 2,
): Uint8ClampedArray {
  if (width <= 2 * radius || height <= 2 * radius || rgba.length !== width * height * 4) {
    return new Uint8ClampedArray(width * height * 4);
  }
  const mask = new Uint8ClampedArray(width * height * 4);
  for (let y = radius; y < height - radius; y++) {
    for (let x = radius; x < width - radius; x++) {
      const i = y * width + x;
      let full = true;
      for (let dy = -radius; dy <= radius && full; dy++) {
        for (let dx = -radius; dx <= radius; dx++) {
          if (rgba[4 * (i + dy * width + dx) + 3] !== 255) {
            full = false;
            break;
          }
        }
      }
      if (full) mask[4 * i + 3] = 255;
    }
  }
  return mask;
}

/**
 * 在根带内把基线 RGB 换成精确采样色，并保持基线 alpha。
 * direct 只消费 alpha：它来自更保守的内缩源，用来限制可换色支持域。
 */
export function renderProtectedRootColors(
  base: PlaneData,
  direct: PlaneData,
  nailLength: number,
  sampler: (x: number, y: number) => Float64Array,
): Uint8ClampedArray {
  const w = base.width, h = base.height;
  if (
    direct.width !== w || direct.height !== h ||
    base.data.length !== w * h * 4 || direct.data.length !== w * h * 4 ||
    !(nailLength > 0)
  ) throw new Error("protected_root_input_invalid");
  const picks = new Uint8Array(w * h);
  const top = h * 0.5 + nailLength * 0.2;
  const bottom = h * 0.5 + nailLength * 0.5;
  const from = Math.max(1, Math.floor(top));
  const to = Math.min(h - 1, Math.ceil(bottom));
  for (let y = from; y < to; y++) {
    for (let x = 1; x < w - 1; x++) {
      const i = y * w + x;
      let opaque = true;
      for (let dy = -1; dy <= 1 && opaque; dy++) {
        for (let dx = -1; dx <= 1; dx++) {
          const j = 4 * (i + dy * w + dx) + 3;
          if (base.data[j] !== 255 || direct.data[j] !== 255) {
            opaque = false;
            break;
          }
        }
      }
      picks[i] = opaque ? 1 : 0;
    }
  }
  const guarded = base.data.slice();
  const adjacent = (i: number) => [i - 1, i + 1, i - w, i + w];
  for (let y = from; y < to; y++) {
    const weight = clamp01(Math.min(y + 0.5 - top, bottom - y - 0.5));
    if (weight === 0) continue;
    for (let x = 1; x < w - 1; x++) {
      const i = y * w + x;
      if (!picks[i]) continue;
      const neighbors = adjacent(i);
      const boundary = neighbors.some(j => !picks[j]);
      const second = !boundary && neighbors.some(j => adjacent(j).some(k => !picks[k]));
      const taper = boundary ? 1 / 3 : second ? 2 / 3 : 1;
      const rgbNew = sampler(x, y);
      for (let c = 0; c < 3; c++) {
        const k = 4 * i + c, current = base.data[k];
        let lo = 0, hi = 255;
        for (const j of neighbors) {
          if (picks[j] || base.data[4 * j + 3] !== 255) continue;
          const neighbor = base.data[4 * j + c];
          const distance = Math.abs(current - neighbor);
          lo = Math.max(lo, neighbor - distance);
          hi = Math.min(hi, neighbor + distance);
        }
        guarded[k] = Math.round(Math.min(hi, Math.max(lo, current + (rgbNew[c] - current) * weight * taper)));
      }
    }
  }
  return guarded;
}

/** V7 resampleTwo：2px 输出与 1px 输出按物理覆盖宽度平滑混合，alpha 必须逐字节一致。 */
export function blendProtectedRootOutputs(
  primary: PlaneData,
  extended: PlaneData,
  weight: number,
): Uint8ClampedArray {
  const w = primary.width, h = primary.height;
  if (
    extended.width !== w || extended.height !== h ||
    primary.data.length !== w * h * 4 || extended.data.length !== w * h * 4
  ) throw new Error("protected_root_blend_input_invalid");
  const amount = clamp01(weight);
  if (amount === 0) return primary.data;
  if (amount === 1) return extended.data;
  const blended = primary.data.slice();
  for (let i = 0; i < blended.length; i += 4) {
    if (primary.data[i + 3] !== extended.data[i + 3]) {
      throw new Error("protected_root_blend_alpha_mismatch");
    }
    for (let c = 0; c < 3; c++) {
      blended[i + c] = Math.round(primary.data[i + c]
        + amount * (extended.data[i + c] - primary.data[i + c]));
    }
  }
  return blended;
}

/** 仿射映射的显示像素四边形最窄宽度。 */
export function minimumPixelFootprint(matrix: Affine2D): number | null {
  const sum = matrix.a ** 2 + matrix.b ** 2 + matrix.c ** 2 + matrix.d ** 2;
  const det = (matrix.a * matrix.d - matrix.b * matrix.c) ** 2;
  const value = Math.sqrt(2 * det / (sum + Math.sqrt(Math.max(0, sum * sum - 4 * det))));
  return Number.isFinite(value) && value > 0 ? value : null;
}

/** 低于 2 个原像素保持 2px；2—3 个原像素之间平滑过渡到 1px。 */
export function adaptiveRootProtectionWeight(physicalFootprint: number): number {
  if (!Number.isFinite(physicalFootprint) || physicalFootprint <= 0) return 0;
  const t = clamp01(physicalFootprint - 2);
  return t * t * (3 - 2 * t);
}
