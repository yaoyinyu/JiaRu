import type { ImagePixels } from "../nail-image-detection.ts";
import type { NailMask, NailTextureCandidate } from "../nail-texture-recognition/types.ts";
import { isSpecularHighlightPixel } from "../nail-texture-recognition/extract-mask-texture.ts";
import { rgbToLab } from "./color-science.ts";
import type { NailHealthHeuristic } from "./types.ts";

/**
 * 启发式评分权重（和为 1）。
 * 该组权重为预注册假设，无外部效度来源（资料汇编 §2.5 第 4 条：竞品 0–100 评分无公开算法），
 * 不得对外表述为"健康评分"的准确度量。
 */
export const NAIL_HEALTH_WEIGHTS = {
  uniformity: 0.5,
  highlight: 0.3,
  streaking: 0.2,
} as const;

/** L* 的 MAD 归一化尺度：MAD ≥ 12 视为完全不均匀。 */
export const COLOR_MAD_SCALE = 12;

/** 条纹指标归一化尺度：垂直/沿轴梯度比达到 3 时记为 1。 */
export const STREAKING_NORMALIZER = 2;

/** 有效前景像素下限，低于此值判定为采样不足。 */
export const MIN_FOREGROUND_PIXELS = 50;

function clamp01(value: number): number {
  return Math.max(0, Math.min(1, value));
}

function median(values: readonly number[]): number {
  if (values.length === 0) return 0;
  const sorted = [...values].sort((left, right) => left - right);
  const middle = Math.floor(sorted.length / 2);
  return sorted.length % 2 === 0 ? (sorted[middle - 1] + sorted[middle]) / 2 : sorted[middle];
}

function luminanceAt(image: ImagePixels, x: number, y: number): number | null {
  const px = Math.round(x);
  const py = Math.round(y);
  if (px < 0 || py < 0 || px >= image.width || py >= image.height) return null;
  const offset = (py * image.width + px) * 4;
  const data = image.data;
  if (offset + 2 >= data.length) return null;
  const lab = rgbToLab(data[offset], data[offset + 1], data[offset + 2]);
  return lab.L;
}

function rgbAt(image: ImagePixels, x: number, y: number): [number, number, number] | null {
  const px = Math.round(x);
  const py = Math.round(y);
  if (px < 0 || py < 0 || px >= image.width || py >= image.height) return null;
  const offset = (py * image.width + px) * 4;
  const data = image.data;
  if (offset + 2 >= data.length) return null;
  return [data[offset], data[offset + 1], data[offset + 2]];
}

interface MaskForegroundPixel {
  x: number;
  y: number;
  alpha: number;
}

function collectForeground(mask: NailMask, image: ImagePixels): MaskForegroundPixel[] {
  const pixels: MaskForegroundPixel[] = [];
  const scale = mask.scale > 0 ? mask.scale : 1;
  for (let my = 0; my < mask.height; my += 1) {
    for (let mx = 0; mx < mask.width; mx += 1) {
      const alpha = mask.data[my * mask.width + mx];
      if (alpha <= 0) continue;
      const x = mask.originX + mx * scale;
      const y = mask.originY + my * scale;
      if (x < 0 || y < 0 || x >= image.width || y >= image.height) continue;
      pixels.push({ x, y, alpha });
    }
  }
  return pixels;
}

/**
 * 指甲健康启发式：仅使用带 mask 的候选，无 mask 时返回 null。
 *
 * 技术路线调整（相对设计文档 §3.5）：文档把 textureStreaking 写成
 * 「沿甲长轴梯度均值 / 垂直方向梯度均值」，但该式在纵向条纹（沿长轴走行）下会**降低**，
 * 与其自身验收标准「条纹 mask → streaking 升高」矛盾。实现改为语义正确方向：
 * `streaking = clamp01((垂直轴梯度均值 / 沿轴梯度均值 − 1) / 2)`，
 * 即横断面梯度显著高于沿轴梯度时记为条纹。该调整只改指标方向，不改阈值体系与权重。
 */
export function analyzeNailHealthHeuristic(
  image: ImagePixels,
  candidates: readonly NailTextureCandidate[]
): NailHealthHeuristic | null {
  const masked = candidates.filter((candidate) => candidate.mask);
  if (masked.length === 0) return null;

  const warnings: string[] = [];
  const luminances: number[] = [];
  let highlightPixels = 0;
  let foregroundPixels = 0;
  let alongGradientSum = 0;
  let perpendicularGradientSum = 0;
  let gradientSamples = 0;

  for (const candidate of masked) {
    const mask = candidate.mask;
    if (!mask) continue;
    const angle = Number.isFinite(candidate.angle) ? candidate.angle : null;
    if (angle === null) warnings.push("nail_health_axis_unknown");
    const axisCos = angle === null ? 0 : Math.cos(angle);
    const axisSin = angle === null ? 1 : Math.sin(angle);

    for (const pixel of collectForeground(mask, image)) {
      const rgb = rgbAt(image, pixel.x, pixel.y);
      if (!rgb) continue;
      const lab = rgbToLab(rgb[0], rgb[1], rgb[2]);
      luminances.push(lab.L);
      foregroundPixels += 1;
      if (isSpecularHighlightPixel(rgb[0], rgb[1], rgb[2], pixel.alpha)) highlightPixels += 1;

      const alongA = luminanceAt(image, pixel.x + axisCos, pixel.y + axisSin);
      const alongB = luminanceAt(image, pixel.x - axisCos, pixel.y - axisSin);
      const perpA = luminanceAt(image, pixel.x - axisSin, pixel.y + axisCos);
      const perpB = luminanceAt(image, pixel.x + axisSin, pixel.y - axisCos);
      if (alongA !== null && alongB !== null && perpA !== null && perpB !== null) {
        alongGradientSum += Math.abs(alongA - alongB);
        perpendicularGradientSum += Math.abs(perpA - perpB);
        gradientSamples += 1;
      }
    }
  }

  if (foregroundPixels === 0) return null;
  if (foregroundPixels < MIN_FOREGROUND_PIXELS) warnings.push("nail_health_insufficient_foreground");

  const medianL = median(luminances);
  const mad = median(luminances.map((value) => Math.abs(value - medianL)));
  const colorUniformity = clamp01(1 - mad / COLOR_MAD_SCALE);
  const highlightRatio = clamp01(highlightPixels / foregroundPixels);

  let textureStreaking = 0;
  if (gradientSamples > 0) {
    const alongMean = alongGradientSum / gradientSamples;
    const perpendicularMean = perpendicularGradientSum / gradientSamples;
    const ratio = perpendicularMean / Math.max(alongMean, Number.EPSILON);
    textureStreaking = clamp01((ratio - 1) / STREAKING_NORMALIZER);
  }

  const score = Math.round(
    100
    * (NAIL_HEALTH_WEIGHTS.uniformity * colorUniformity
      + NAIL_HEALTH_WEIGHTS.highlight * (1 - highlightRatio)
      + NAIL_HEALTH_WEIGHTS.streaking * (1 - textureStreaking))
  );

  return {
    score,
    colorUniformity,
    highlightRatio,
    textureStreaking,
    warnings: [...new Set(warnings)],
    heuristicOnly: true,
  };
}
