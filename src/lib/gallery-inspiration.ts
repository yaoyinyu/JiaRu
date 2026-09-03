/**
 * 灵感图库 → 编辑器的灵感色推导（纯函数，无 DOM 依赖，可在 Node 测试环境运行）。
 *
 * 背景：/gallery 卡片点击后跳转 /editor?gallery=<id>，但编辑器是「逐指涂纯色」
 * 的试色工具，无法直接套用一张完整美甲图。本模块负责把灵感素材图压缩为该
 * 工具能消费的信息——一个"灵感色"（从素材图采样聚类后按「出现频次 × 饱和度」
 * 加权选出的代表色），并映射到 20 色预设中最接近的一款，供编辑器预涂与推荐。
 *
 * 设计约束：
 * - 不做美甲区域识别（那属于识别模型链路，白皮书 §6）；这里是对整图采样的
 *   启发式推导，只作灵感参考，不宣称等于素材中的甲油颜色。
 * - 与 PRESET_COLORS（src/lib/utils.ts）保持只读依赖，不得修改预设表。
 */

import { PRESET_COLORS } from "./utils.ts";

/** 采样像素（0-255 RGB）。 */
export type RgbPixel = { r: number; g: number; b: number };

/** 灵感色推导结果。 */
export type InspiredSwatch = {
  /** 簇平均色，形如 "#RRGGBB"（小写）。 */
  hex: string;
  /** 该簇占全部采样像素的比例（0~1）。 */
  ratio: number;
  /** 该簇平均色的 HSL 饱和度（0~1）。 */
  saturation: number;
};

/** 就近预设色匹配结果（PRESET_COLORS 条目的引用）。 */
export type PresetMatch = { name: string; color: string };

/** 量化位数：每通道只取高 4 位 → 4096 个颜色桶。 */
const CHANNEL_SHIFT = 4;

/** 加权距离的通道权重（接近感知亮度：绿 > 红 > 蓝）。 */
const CHANNEL_WEIGHTS = { r: 2, g: 4, b: 3 } as const;

function clamp255(value: number): number {
  return Math.max(0, Math.min(255, Math.round(value)));
}

/** RGB → "#RRGGBB"（自动截断到 0-255）。 */
export function toHexColor(r: number, g: number, b: number): string {
  const part = (v: number) =>
    clamp255(v).toString(16).padStart(2, "0");
  return `#${part(r)}${part(g)}${part(b)}`;
}

/** RGB 的 HSL 饱和度（0~1；无彩色（含纯黑纯白）定义为 0）。 */
export function saturationOf(r: number, g: number, b: number): number {
  const max = Math.max(r, g, b) / 255;
  const min = Math.min(r, g, b) / 255;
  if (max === min) return 0;
  return (max - min) / (1 - Math.abs(2 * ((max + min) / 2) - 1));
}

/**
 * 从 RGBA 像素缓冲（如 canvas getImageData().data）抽取不透明采样像素。
 * alpha 低于阈值的像素（透明/半透明边缘）会被跳过。
 */
export function pixelsFromRgbaBuffer(
  data: Uint8ClampedArray,
  alphaThreshold = 128
): RgbPixel[] {
  const pixels: RgbPixel[] = [];
  for (let i = 0; i + 3 < data.length; i += 4) {
    if (data[i + 3] < alphaThreshold) continue;
    pixels.push({ r: data[i], g: data[i + 1], b: data[i + 2] });
  }
  return pixels;
}

/**
 * 从采样像素推导灵感色：按「每通道高 4 位」量化聚类，取簇平均色，
 * 以「簇像素数 × (0.25 + 饱和度)」打分选出胜者。低饱和权底 0.25 保证
 * 大面积主色（如法式白边的白色甲尖）不会被少量鲜艳噪点轻易压过，
 * 同时让饱和度更高的簇（甲彩色 vs 皮肤/背景）在数量接近时胜出。
 * 返回 null 表示没有可用采样。
 */
export function pickInspiredSwatch(pixels: RgbPixel[]): InspiredSwatch | null {
  if (pixels.length === 0) return null;

  type Bucket = { sumR: number; sumG: number; sumB: number; count: number };
  const buckets = new Map<number, Bucket>();
  for (const p of pixels) {
    const key =
      ((p.r >> CHANNEL_SHIFT) << 8) |
      ((p.g >> CHANNEL_SHIFT) << 4) |
      (p.b >> CHANNEL_SHIFT);
    const bucket = buckets.get(key) ?? { sumR: 0, sumG: 0, sumB: 0, count: 0 };
    bucket.sumR += p.r;
    bucket.sumG += p.g;
    bucket.sumB += p.b;
    bucket.count += 1;
    buckets.set(key, bucket);
  }

  let best: Bucket | null = null;
  let bestScore = -1;
  for (const bucket of buckets.values()) {
    const r = bucket.sumR / bucket.count;
    const g = bucket.sumG / bucket.count;
    const b = bucket.sumB / bucket.count;
    const score = bucket.count * (0.25 + saturationOf(r, g, b));
    if (score > bestScore) {
      bestScore = score;
      best = bucket;
    }
  }
  if (!best) return null;

  const r = best.sumR / best.count;
  const g = best.sumG / best.count;
  const b = best.sumB / best.count;
  return {
    hex: toHexColor(r, g, b),
    ratio: best.count / pixels.length,
    saturation: saturationOf(r, g, b),
  };
}

/** 解析 "#RRGGBB"（大小写均可），非法输入返回 null。 */
export function parseHexColor(hex: string): RgbPixel | null {
  const match = /^#([0-9a-f]{6})$/i.exec(hex.trim());
  if (!match) return null;
  const value = Number.parseInt(match[1], 16);
  return {
    r: (value >> 16) & 0xff,
    g: (value >> 8) & 0xff,
    b: value & 0xff,
  };
}

/**
 * 在 PRESET_COLORS 中找与给定 hex 最接近的预设色（跳过无法解析的条目，
 * 例如「透明」的 rgba 值）。加权平方距离近似感知色差。无匹配返回 null。
 */
export function closestPresetColor(hex: string): PresetMatch | null {
  const target = parseHexColor(hex);
  if (!target) return null;
  let best: PresetMatch | null = null;
  let bestDistance = Number.POSITIVE_INFINITY;
  for (const preset of PRESET_COLORS) {
    const candidate = parseHexColor(preset.color);
    if (!candidate) continue;
    const distance =
      CHANNEL_WEIGHTS.r * (candidate.r - target.r) ** 2 +
      CHANNEL_WEIGHTS.g * (candidate.g - target.g) ** 2 +
      CHANNEL_WEIGHTS.b * (candidate.b - target.b) ** 2;
    if (distance < bestDistance) {
      bestDistance = distance;
      best = { name: preset.name, color: preset.color };
    }
  }
  return best;
}
