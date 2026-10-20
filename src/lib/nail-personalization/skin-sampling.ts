import type { ImagePixels } from "../nail-image-detection.ts";
import type { NailMask, NailTextureCandidate } from "../nail-texture-recognition/types.ts";
import { rgbToLab } from "./color-science.ts";

/** 环采样几何（相对甲面椭圆半轴的倍数）。 */
export const RING_SCALES = [1.15, 1.35, 1.6] as const;
export const ANGULAR_STEPS = 24;

/** 采样数绝对下限（预注册假设，标定要求见设计文档 §8）。 */
export const MIN_SKIN_SAMPLES = 120;
export const MIN_SKIN_SAMPLES_SINGLE_CANDIDATE = 60;

/** quality 门（与 MIN_SKIN_SAMPLES 构成双条件，任一不满足即判定采样不可用）。 */
export const SKIN_QUALITY_MIN = 0.35;

const DEFAULT_EXPECTED_CANDIDATES = 5;

export interface PeriNailSample {
  lab: { L: number; a: number; b: number };
  sampleCount: number;
  quality: number;
  warnings: string[];
}

interface SampleGeometry {
  cx: number;
  cy: number;
  halfLong: number;
  halfShort: number;
  angle: number;
}

function clamp01(value: number): number {
  return Math.max(0, Math.min(1, value));
}

/** 甲面几何：有 mask 时用 mask 前景包围盒推导半轴（膨胀环的近似），否则用候选椭圆。 */
function resolveGeometry(candidate: NailTextureCandidate): SampleGeometry | null {
  const base = {
    cx: candidate.cx,
    cy: candidate.cy,
    halfLong: candidate.length / 2,
    halfShort: candidate.width / 2,
    angle: Number.isFinite(candidate.angle) ? candidate.angle : 0,
  };
  if (!Number.isFinite(base.halfLong) || !Number.isFinite(base.halfShort)) return null;
  if (base.halfLong <= 0 || base.halfShort <= 0) return null;

  const mask = candidate.mask;
  if (!mask) return base;

  const bounds = maskForegroundBounds(mask);
  if (!bounds) return base;

  const halfWidth = bounds.width / 2;
  const halfHeight = bounds.height / 2;
  // 用包围盒长边对齐长轴：mask 不提供朝向，属有依据的近似而非精确甲面轮廓。
  if (halfHeight >= halfWidth) {
    return { cx: candidate.cx, cy: candidate.cy, halfLong: halfHeight, halfShort: halfWidth, angle: base.angle };
  }
  return {
    cx: candidate.cx,
    cy: candidate.cy,
    halfLong: halfWidth,
    halfShort: halfHeight,
    angle: base.angle + Math.PI / 2,
  };
}

function maskForegroundBounds(mask: NailMask): { width: number; height: number } | null {
  let minX = Number.POSITIVE_INFINITY;
  let minY = Number.POSITIVE_INFINITY;
  let maxX = Number.NEGATIVE_INFINITY;
  let maxY = Number.NEGATIVE_INFINITY;
  let foreground = 0;
  for (let y = 0; y < mask.height; y += 1) {
    for (let x = 0; x < mask.width; x += 1) {
      if (mask.data[y * mask.width + x] <= 0) continue;
      foreground += 1;
      if (x < minX) minX = x;
      if (x > maxX) maxX = x;
      if (y < minY) minY = y;
      if (y > maxY) maxY = y;
    }
  }
  if (foreground === 0) return null;
  const width = (maxX - minX + 1) * Math.max(mask.scale, Number.EPSILON);
  const height = (maxY - minY + 1) * Math.max(mask.scale, Number.EPSILON);
  if (width <= 0 || height <= 0) return null;
  return { width, height };
}

/** 放宽版 YCbCr 肤色判据（常量复制自局部近景检测实现思路，见设计文档 §3.3 实现约束）。 */
export function isSkinPixelRgb(r: number, g: number, b: number): boolean {
  const y = 0.299 * r + 0.587 * g + 0.114 * b;
  const cb = 128 - 0.168736 * r - 0.331264 * g + 0.5 * b;
  const cr = 128 + 0.5 * r - 0.418688 * g - 0.081312 * b;
  return y > 40 && cb >= 77 && cb <= 145 && cr >= 125 && cr <= 180;
}

function pixelAt(image: ImagePixels, x: number, y: number): [number, number, number] | null {
  const px = Math.round(x);
  const py = Math.round(y);
  if (px < 0 || py < 0 || px >= image.width || py >= image.height) return null;
  const offset = (py * image.width + px) * 4;
  const data = image.data;
  if (offset + 2 >= data.length) return null;
  return [data[offset], data[offset + 1], data[offset + 2]];
}

/** 点是否落在任一甲面椭圆内部或邻甲安全距离内（甲面自污染排除）。 */
function isContaminated(
  x: number,
  y: number,
  geometries: readonly SampleGeometry[]
): boolean {
  for (const geometry of geometries) {
    const dx = x - geometry.cx;
    const dy = y - geometry.cy;
    // 邻甲安全距离取半短轴：环采样最内圈（1.15×）位于该距离之外，不会被自身甲面误伤。
    if (Math.hypot(dx, dy) < geometry.halfShort) return true;
    const cos = Math.cos(-geometry.angle);
    const sin = Math.sin(-geometry.angle);
    const u = dx * cos - dy * sin;
    const v = dx * sin + dy * cos;
    const normalized = (u / geometry.halfLong) ** 2 + (v / geometry.halfShort) ** 2;
    if (normalized <= 1) return true;
  }
  return false;
}

function median(values: readonly number[]): number {
  if (values.length === 0) return 0;
  const sorted = [...values].sort((left, right) => left - right);
  const middle = Math.floor(sorted.length / 2);
  return sorted.length % 2 === 0 ? (sorted[middle - 1] + sorted[middle]) / 2 : sorted[middle];
}

/**
 * 甲周肤色环采样。仅在候选包围盒附近取点，不扫全图。
 * 采样点落在甲面/邻甲内、或越界时被剔除，且不计入分母（甲面自污染排除）。
 */
export function samplePeriNailSkin(
  image: ImagePixels,
  candidates: readonly NailTextureCandidate[],
  options?: { ringScale?: number; expectedCandidates?: number }
): PeriNailSample {
  const expectedCandidates = Math.max(1, options?.expectedCandidates ?? DEFAULT_EXPECTED_CANDIDATES);
  const geometries: SampleGeometry[] = [];
  for (const candidate of candidates) {
    const geometry = resolveGeometry(candidate);
    if (geometry) geometries.push(geometry);
  }

  if (geometries.length === 0) {
    return {
      lab: { L: 0, a: 0, b: 0 },
      sampleCount: 0,
      quality: 0,
      warnings: ["skin_sampling_no_candidates"],
    };
  }

  const ringScale = options?.ringScale ?? 1;
  const labs: Array<{ L: number; a: number; b: number }> = [];
  let considered = 0;

  for (const geometry of geometries) {
    const cos = Math.cos(geometry.angle);
    const sin = Math.sin(geometry.angle);
    for (let step = 0; step < ANGULAR_STEPS; step += 1) {
      const theta = (step / ANGULAR_STEPS) * Math.PI * 2;
      const cosTheta = Math.cos(theta);
      const sinTheta = Math.sin(theta);
      for (const scale of RING_SCALES) {
        const u = geometry.halfLong * scale * ringScale * cosTheta;
        const v = geometry.halfShort * scale * ringScale * sinTheta;
        const x = geometry.cx + u * cos - v * sin;
        const y = geometry.cy + u * sin + v * cos;
        if (isContaminated(x, y, geometries)) continue;
        const pixel = pixelAt(image, x, y);
        if (!pixel) continue;
        considered += 1;
        const [r, g, b] = pixel;
        if (!isSkinPixelRgb(r, g, b)) continue;
        labs.push(rgbToLab(r, g, b));
      }
    }
  }

  const sampleCount = labs.length;
  const skinRatio = considered > 0 ? sampleCount / considered : 0;
  const coverage = clamp01(geometries.length / expectedCandidates);
  const quality = clamp01(skinRatio * coverage);

  const minSamples = geometries.length <= 1 ? MIN_SKIN_SAMPLES_SINGLE_CANDIDATE : MIN_SKIN_SAMPLES;
  const warnings: string[] = [];
  if (sampleCount < minSamples) warnings.push("skin_sampling_low_quality");
  if (quality < SKIN_QUALITY_MIN) warnings.push("skin_sampling_low_quality");

  return {
    lab: {
      L: median(labs.map((lab) => lab.L)),
      a: median(labs.map((lab) => lab.a)),
      b: median(labs.map((lab) => lab.b)),
    },
    sampleCount,
    quality,
    warnings: [...new Set(warnings)],
  };
}
