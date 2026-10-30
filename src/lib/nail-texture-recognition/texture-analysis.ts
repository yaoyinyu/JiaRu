import type { NailShapeClass } from "../ar-nail-shape.ts";
import { labDistance, rgbToLab, type Lab } from "../nail-personalization/color-science.ts";
import { inspectSpecularHighlights, isSpecularHighlightPixel } from "./extract-mask-texture.ts";

/**
 * 提取纹理的参数分析（颜色 / 图案 / 光泽度 / 甲型）。
 *
 * 输入是 extractNormalizedNailTexture 产出的位图：≤256px、直通 alpha（非预乘）、
 * 已按「甲尖朝上、甲面充满位图」归一化，因此行宽剖面可直接用于甲型分类。
 * 全部为浏览器端启发式统计，结果用于渲染参数匹配与界面展示参考。
 */

export type NailPatternClass = "solid" | "gradient" | "french" | "glitter" | "pattern";

export interface NailDominantColor {
  hex: string;
  ratio: number;
}

export interface NailTextureProfile {
  shape: NailShapeClass;
  /** 0..1，按分类阈值边距给出；0 表示无法可靠判型 */
  shapeConfidence: number;
  /** 内容高 / 最大行宽 */
  shapeAspectRatio: number;
  dominantColors: NailDominantColor[];
  pattern: NailPatternClass;
  /** 0..1，高光占比代理指标 */
  gloss: number;
  warnings: string[];
}

export const ANALYSIS_WARNING_SHAPE_UNKNOWN = "analysis_shape_unknown";
export const ANALYSIS_WARNING_LOW_OPACITY = "analysis_low_opacity";

export interface AnalyzeNailTextureOptions {
  /** 提取诊断中的高光比提示；传入时优先于模块内自算 */
  highlightRatioHint?: number | null;
}

export interface WidthProfileShapeResult {
  shape: NailShapeClass;
  confidence: number;
  aspectRatio: number;
  tipRatio: number;
}

// 甲型分类阈值：tipRatio = 尖部行宽中位数 / 根部行宽中位数，aspect = 内容高 / 最大行宽。
const SQUARE_TIP_RATIO = 0.8;
const STILETTO_TIP_RATIO = 0.25;
const SHORT_ASPECT = 1.2;
const ALMOND_ASPECT = 1.45;

function median(values: readonly number[]): number {
  if (values.length === 0) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  const mid = sorted.length >> 1;
  return sorted.length % 2 === 1
    ? sorted[mid] ?? 0
    : ((sorted[mid - 1] ?? 0) + (sorted[mid] ?? 0)) / 2;
}

function clamp01(value: number): number {
  return Math.max(0, Math.min(1, value));
}

/** 边距归一化：margin 达到 scale 记满分 */
function margin01(margin: number, scale: number): number {
  return clamp01(margin / scale);
}

function toHex(r: number, g: number, b: number): string {
  const part = (value: number) =>
    Math.max(0, Math.min(255, Math.round(value))).toString(16).padStart(2, "0");
  return `#${part(r)}${part(g)}${part(b)}`;
}

/**
 * 纯函数：按行宽剖面分类甲型。widths[0] 为甲尖行。
 * 有效行不足时返回 confidence 0（调用方据此加 SHAPE_UNKNOWN 告警）。
 */
export function classifyNailShapeFromWidthProfile(
  widths: readonly number[]
): WidthProfileShapeResult {
  const validRows: number[] = [];
  for (const width of widths) {
    if (width >= 1) validRows.push(width);
  }
  if (validRows.length < 8) {
    const maxWidth = Math.max(0, ...widths);
    return {
      shape: "round",
      confidence: 0,
      aspectRatio: maxWidth > 0 ? validRows.length / maxWidth : 0,
      tipRatio: 0,
    };
  }

  const baseBand = median(
    validRows.slice(Math.floor(validRows.length * 0.75))
  );
  const tipBand = median(validRows.slice(0, Math.ceil(validRows.length * 0.15)));
  const maxWidth = Math.max(...validRows);
  const aspectRatio = validRows.length / Math.max(1, maxWidth);
  const tipRatio = baseBand > 0 ? tipBand / baseBand : 0;

  if (tipRatio >= SQUARE_TIP_RATIO) {
    return {
      shape: "square",
      confidence: margin01(tipRatio - SQUARE_TIP_RATIO, 0.12),
      aspectRatio,
      tipRatio,
    };
  }
  if (aspectRatio < SHORT_ASPECT) {
    return {
      shape: "round",
      confidence: margin01(SHORT_ASPECT - aspectRatio, 0.15),
      aspectRatio,
      tipRatio,
    };
  }
  if (tipRatio < STILETTO_TIP_RATIO) {
    return {
      shape: "stiletto",
      confidence: margin01(STILETTO_TIP_RATIO - tipRatio, 0.1),
      aspectRatio,
      tipRatio,
    };
  }
  if (aspectRatio >= ALMOND_ASPECT) {
    return {
      shape: "almond",
      confidence: margin01(
        Math.min(aspectRatio - ALMOND_ASPECT, 0.55 - tipRatio),
        0.15
      ),
      aspectRatio,
      tipRatio,
    };
  }
  return {
    shape: "round",
    confidence: margin01(
      Math.min(ALMOND_ASPECT - aspectRatio, tipRatio - 0.55),
      0.12
    ),
    aspectRatio,
    tipRatio,
  };
}

interface ColorStatistics {
  colors: NailDominantColor[];
  bandLabs: Lab[];
  speckRatio: number;
  speckRunCount: number;
  averageSpeckRunLength: number;
}

const BUCKET_COUNT = 4096;
const BAND_COUNT = 4;

function luminance(r: number, g: number, b: number): number {
  return r * 0.299 + g * 0.587 + b * 0.114;
}

function analyzeColors(imageData: ImageData): ColorStatistics {
  const { width, height, data } = imageData;
  const counts = new Int32Array(BUCKET_COUNT);
  const sumR = new Float64Array(BUCKET_COUNT);
  const sumG = new Float64Array(BUCKET_COUNT);
  const sumB = new Float64Array(BUCKET_COUNT);

  const bandPixelCount = new Int32Array(BAND_COUNT);
  const bandLumSum = new Float64Array(BAND_COUNT);
  const bandRgbSum = new Float64Array(BAND_COUNT * 3);

  let opaqueCount = 0;
  let speckCount = 0;
  let speckRunCount = 0;
  let speckRunTotalLength = 0;

  for (let y = 0; y < height; y += 1) {
    const band = Math.min(
      BAND_COUNT - 1,
      Math.floor((y / Math.max(1, height)) * BAND_COUNT)
    );
    let rowSpeckRunLength = 0;
    for (let x = 0; x < width; x += 1) {
      const offset = (y * width + x) * 4;
      const alpha = data[offset + 3] ?? 0;
      if (alpha < 128) continue;
      const r = data[offset] ?? 0;
      const g = data[offset + 1] ?? 0;
      const b = data[offset + 2] ?? 0;
      opaqueCount += 1;
      const lum = luminance(r, g, b);

      if (isSpecularHighlightPixel(r, g, b, alpha)) {
        // 高光像素不参与主色/带均值/亮斑统计（否则平滑高光区会被误判为亮片）。
        continue;
      }

      const bucket =
        ((r >> 4) << 8) | ((g >> 4) << 4) | (b >> 4);
      counts[bucket] += 1;
      sumR[bucket] += r;
      sumG[bucket] += g;
      sumB[bucket] += b;

      bandPixelCount[band] += 1;
      bandLumSum[band] += lum;
      bandRgbSum[band * 3] += r;
      bandRgbSum[band * 3 + 1] += g;
      bandRgbSum[band * 3 + 2] += b;

      // 亮斑基线用已统计像素的滚动均值（首行用全局 0.6 近似，避免 band0 全零）。
      const baseline =
        bandPixelCount[band] > 8
          ? bandLumSum[band] / bandPixelCount[band]
          : 153;
      if (lum > baseline + 40) {
        speckCount += 1;
        rowSpeckRunLength += 1;
      } else if (rowSpeckRunLength > 0) {
        speckRunCount += 1;
        speckRunTotalLength += rowSpeckRunLength;
        rowSpeckRunLength = 0;
      }
    }
    if (rowSpeckRunLength > 0) {
      speckRunCount += 1;
      speckRunTotalLength += rowSpeckRunLength;
    }
  }

  const bucketList: Array<{ bucket: number; count: number }> = [];
  for (let bucket = 0; bucket < BUCKET_COUNT; bucket += 1) {
    if (counts[bucket] > 0) bucketList.push({ bucket, count: counts[bucket] });
  }
  bucketList.sort((a, b) => b.count - a.count);

  const colors: NailDominantColor[] = [];
  for (const item of bucketList) {
    if (colors.length >= 3) break;
    const r = sumR[item.bucket] / item.count;
    const g = sumG[item.bucket] / item.count;
    const b = sumB[item.bucket] / item.count;
    const lab = rgbToLab(r, g, b);
    const duplicate = colors.some((existing) => {
      const er = parseInt(existing.hex.slice(1, 3), 16);
      const eg = parseInt(existing.hex.slice(3, 5), 16);
      const eb = parseInt(existing.hex.slice(5, 7), 16);
      return labDistance(lab, rgbToLab(er, eg, eb)) < 10;
    });
    if (duplicate) continue;
    colors.push({ hex: toHex(r, g, b), ratio: item.count / Math.max(1, opaqueCount) });
  }
  if (colors.length === 0 && opaqueCount > 0) {
    colors.push({ hex: "#E8A0BF", ratio: 1 });
  }

  const bandLabs: Lab[] = [];
  for (let band = 0; band < BAND_COUNT; band += 1) {
    const count = Math.max(1, bandPixelCount[band]);
    bandLabs.push(
      rgbToLab(
        bandRgbSum[band * 3] / count,
        bandRgbSum[band * 3 + 1] / count,
        bandRgbSum[band * 3 + 2] / count
      )
    );
  }

  return {
    colors,
    bandLabs,
    speckRatio: opaqueCount > 0 ? speckCount / opaqueCount : 0,
    speckRunCount,
    averageSpeckRunLength:
      speckRunCount > 0 ? speckRunTotalLength / speckRunCount : 0,
  };
}

function decidePattern(stats: ColorStatistics): NailPatternClass {
  const { bandLabs, colors, speckRatio, speckRunCount, averageSpeckRunLength } = stats;

  if (
    speckRatio >= 0.01 &&
    speckRatio <= 0.45 &&
    speckRunCount >= 30 &&
    averageSpeckRunLength <= 6
  ) {
    return "glitter";
  }

  const jumps = [
    labDistance(bandLabs[0], bandLabs[1]),
    labDistance(bandLabs[1], bandLabs[2]),
    labDistance(bandLabs[2], bandLabs[3]),
  ];
  const tipBaseDistance = labDistance(bandLabs[0], bandLabs[3]);

  // 法式：尖部与根部色差大，且色差集中在尖部第一条带（锐利分界）。
  if (
    tipBaseDistance >= 18 &&
    jumps[0] >= 12 &&
    jumps[0] >= jumps[1] * 1.5 &&
    jumps[0] >= jumps[2] * 1.5
  ) {
    return "french";
  }

  // 渐变：相邻带色差持续存在且亮度单调。
  const lumTrend =
    bandLabs[3].L - bandLabs[0].L;
  const monotonicLum =
    (bandLabs[0].L <= bandLabs[1].L && bandLabs[1].L <= bandLabs[2].L) ||
    (bandLabs[0].L >= bandLabs[1].L && bandLabs[1].L >= bandLabs[2].L);
  if (jumps.every((jump) => jump >= 5) && monotonicLum && Math.abs(lumTrend) >= 8) {
    return "gradient";
  }

  const maxBandDistance = Math.max(
    tipBaseDistance,
    jumps[0],
    jumps[1],
    jumps[2]
  );
  if ((colors[0]?.ratio ?? 0) >= 0.7 || maxBandDistance < 12) {
    return "solid";
  }
  return "pattern";
}

async function textureToImageData(texture: ImageBitmap): Promise<ImageData> {
  const canvas = new OffscreenCanvas(texture.width, texture.height);
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  if (!ctx) throw new Error("canvas_2d_unavailable");
  ctx.drawImage(
    texture,
    0,
    0,
    texture.width,
    texture.height,
    0,
    0,
    texture.width,
    texture.height
  );
  return ctx.getImageData(0, 0, texture.width, texture.height);
}

function lowOpacityProfile(warnings: string[]): NailTextureProfile {
  return {
    shape: "round",
    shapeConfidence: 0,
    shapeAspectRatio: 0,
    dominantColors: [{ hex: "#E8A0BF", ratio: 1 }],
    pattern: "solid",
    gloss: 0,
    warnings: [...warnings, ANALYSIS_WARNING_LOW_OPACITY],
  };
}

export async function analyzeNailTextureProfile(
  texture: ImageBitmap,
  options: AnalyzeNailTextureOptions = {}
): Promise<NailTextureProfile> {
  const warnings: string[] = [];
  const imageData = await textureToImageData(texture);

  const widths: number[] = new Array(imageData.height).fill(0);
  let opaqueCount = 0;
  for (let y = 0; y < imageData.height; y += 1) {
    for (let x = 0; x < imageData.width; x += 1) {
      const alpha = imageData.data[(y * imageData.width + x) * 4 + 3] ?? 0;
      if (alpha < 128) continue;
      widths[y] += 1;
      opaqueCount += 1;
    }
  }
  if (opaqueCount < 64) return lowOpacityProfile(warnings);

  const shapeResult = classifyNailShapeFromWidthProfile(widths);
  if (shapeResult.confidence === 0) {
    warnings.push(ANALYSIS_WARNING_SHAPE_UNKNOWN);
  }

  const hint = options.highlightRatioHint;
  const gloss =
    typeof hint === "number" && Number.isFinite(hint)
      ? clamp01(hint)
      : clamp01(inspectSpecularHighlights(imageData).highlightRatio / 0.06);

  const stats = analyzeColors(imageData);
  const pattern = decidePattern(stats);

  return {
    shape: shapeResult.shape,
    shapeConfidence: shapeResult.confidence,
    shapeAspectRatio: shapeResult.aspectRatio,
    dominantColors: stats.colors,
    pattern,
    gloss,
    warnings,
  };
}
