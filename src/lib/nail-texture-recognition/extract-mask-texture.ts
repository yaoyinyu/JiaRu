import type { NailMask } from "./types.ts";
import {
  estimateMaskPrincipalAngle,
  resolveMaskTextureRotation,
  type MaskTextureRotationSource,
} from "./mask-orientation.ts";

const MAX_TEXTURE_SIZE = 256;
const DEFAULT_FEATHER_RADIUS = 2;
const DEFAULT_HIGHLIGHT_SEARCH_RADIUS = 3;
/** 归一化紧致裁剪时在 alpha 边界外保留的像素边距，避免软边被硬切。 */
const NORMALIZATION_EDGE_PAD = 2;

export interface MaskBounds {
  minX: number;
  minY: number;
  maxX: number;
  maxY: number;
}

export interface MaskExtractionQualitySummary {
  ok: boolean;
  foregroundPixels: number;
  boundsArea: number;
  fillRatio: number;
  touchesEdge: boolean;
  warnings: string[];
}

export interface TextureHighlightRepairSummary {
  strategy?: "preserve" | "repair";
  highlightPixels: number;
  repairedPixels: number;
  highlightRatio: number;
}

export interface TextureNormalizationInfo {
  /** 解析出的甲面横轴全角（弧度）；实际应用到位图的旋转为 -rotationRadians。 */
  rotationRadians: number;
  source: MaskTextureRotationSource;
  warnings: string[];
}

export interface TextureExtractionDiagnostics {
  quality: MaskExtractionQualitySummary;
  highlightRepair: TextureHighlightRepairSummary;
  /** 仅 extractNormalizedNailTexture 填写；既有提取路径保持缺省。 */
  normalization?: TextureNormalizationInfo;
}

export interface ExtractedMaskTexture {
  texture: ImageBitmap;
  diagnostics: TextureExtractionDiagnostics;
}

export function findMaskBounds(mask: NailMask, includeCoverage = false): MaskBounds | null {
  let minX = mask.width;
  let minY = mask.height;
  let maxX = -1;
  let maxY = -1;

  for (let y = 0; y < mask.height; y++) {
    for (let x = 0; x < mask.width; x++) {
      if (!mask.data[y * mask.width + x] && !(includeCoverage && mask.coverageAlpha?.length === mask.data.length && mask.coverageAlpha[y * mask.width + x])) continue;
      minX = Math.min(minX, x);
      minY = Math.min(minY, y);
      maxX = Math.max(maxX, x);
      maxY = Math.max(maxY, y);
    }
  }

  if (maxX < minX || maxY < minY) return null;
  return { minX, minY, maxX, maxY };
}

export function buildFeatheredAlphaMask(
  mask: NailMask,
  featherRadius: number = DEFAULT_FEATHER_RADIUS
): Uint8ClampedArray {
  if (mask.coverageAlpha) {
    if (mask.coverageAlpha.length !== mask.width * mask.height) throw new Error("coverage_alpha_shape_mismatch");
    return new Uint8ClampedArray(mask.coverageAlpha);
  }
  const alpha = new Uint8ClampedArray(mask.width * mask.height);
  const radius = Math.max(0, Math.floor(featherRadius));

  for (let y = 0; y < mask.height; y++) {
    for (let x = 0; x < mask.width; x++) {
      const index = y * mask.width + x;
      if (!mask.data[index]) {
        alpha[index] = 0;
        continue;
      }

      if (radius === 0) {
        alpha[index] = 255;
        continue;
      }

      let minBackgroundDistance = Number.POSITIVE_INFINITY;
      for (let offsetY = -radius; offsetY <= radius; offsetY++) {
        for (let offsetX = -radius; offsetX <= radius; offsetX++) {
          const sampleX = x + offsetX;
          const sampleY = y + offsetY;
          if (sampleX < 0 || sampleY < 0 || sampleX >= mask.width || sampleY >= mask.height) {
            minBackgroundDistance = Math.min(
              minBackgroundDistance,
              Math.hypot(offsetX, offsetY)
            );
            continue;
          }
          if (mask.data[sampleY * mask.width + sampleX]) continue;
          minBackgroundDistance = Math.min(
            minBackgroundDistance,
            Math.hypot(offsetX, offsetY)
          );
        }
      }

      if (!Number.isFinite(minBackgroundDistance) || minBackgroundDistance >= radius) {
        alpha[index] = 255;
        continue;
      }

      alpha[index] = Math.max(
        0,
        Math.min(255, Math.round((minBackgroundDistance / radius) * 255))
      );
    }
  }

  // 软边来源（本机精细抠图）在 `alpha` 中携带 0..255 的真实边缘权重：
  // 取 min(软边, 羽化斜坡) —— 几何仍由二值 `data` 决定，软边只能收紧不能扩张。
  // 长度不匹配时整体忽略，避免短数组产生 NaN 或静默全透明。
  const soft = mask.alpha;
  if (soft && soft.length === alpha.length) {
    for (let index = 0; index < alpha.length; index += 1) {
      if (soft[index] < alpha[index]) alpha[index] = soft[index];
    }
  }

  return alpha;
}

const ALPHA_RAMP_LOW = 0.38;
const ALPHA_RAMP_HIGH = 0.62;

/**
 * 收紧 alpha 半透明带。
 *
 * 掩膜在检测域（最长边 800）上生成，放大到原图纹理后边缘过渡可宽达 3–5 像素；
 * 这段宽过渡既让轮廓发虚，也把甲面外的肤色保留成半透明彩边。这里用对称
 * smoothstep 把 [0.38, 0.62] 映射到 [0, 1]：50% 等值线位置不变（几何不漂移），
 * 过渡带压到约 1 像素，等同于一次正确的抗锯齿重建。
 */
export function tightenAlphaRamp(alpha: Uint8ClampedArray): Uint8ClampedArray {
  const out = new Uint8ClampedArray(alpha.length);
  const span = ALPHA_RAMP_HIGH - ALPHA_RAMP_LOW;
  for (let index = 0; index < alpha.length; index += 1) {
    const value = alpha[index] / 255;
    if (value <= ALPHA_RAMP_LOW) {
      out[index] = 0;
      continue;
    }
    if (value >= ALPHA_RAMP_HIGH) {
      out[index] = 255;
      continue;
    }
    const t = (value - ALPHA_RAMP_LOW) / span;
    out[index] = Math.round(255 * t * t * (3 - 2 * t));
  }
  return out;
}

/**
 * 对 alpha 做一次 3×3 高斯平滑（[1,2,1] 可分离卷积）。
 * 用于生成平滑提议，最终透明度由提取阶段的覆盖率保护约束。
 */
export function smoothAlphaBoundary(
  alpha: Uint8ClampedArray,
  width: number,
  height: number
): Uint8ClampedArray {
  if (width <= 2 || height <= 2) return new Uint8ClampedArray(alpha);
  const horizontal = new Uint8ClampedArray(alpha.length);
  for (let y = 0; y < height; y += 1) {
    const row = y * width;
    for (let x = 0; x < width; x += 1) {
      const left = alpha[row + Math.max(0, x - 1)];
      const center = alpha[row + x];
      const right = alpha[row + Math.min(width - 1, x + 1)];
      horizontal[row + x] = Math.round((left + center * 2 + right) / 4);
    }
  }
  const out = new Uint8ClampedArray(alpha.length);
  for (let y = 0; y < height; y += 1) {
    const up = Math.max(0, y - 1) * width;
    const row = y * width;
    const down = Math.min(height - 1, y + 1) * width;
    for (let x = 0; x < width; x += 1) {
      out[row + x] = Math.round(
        (horizontal[up + x] + horizontal[row + x] * 2 + horizontal[down + x]) / 4
      );
    }
  }
  return out;
}

export function summarizeMaskExtractionQuality(mask: NailMask): MaskExtractionQualitySummary {
  const bounds = findMaskBounds(mask);
  if (!bounds) {
    return {
      ok: false,
      foregroundPixels: 0,
      boundsArea: 0,
      fillRatio: 0,
      touchesEdge: false,
      warnings: ["mask_has_no_foreground_pixels"],
    };
  }

  const foregroundPixels = Array.from(mask.data).reduce((sum, value) => sum + (value ? 1 : 0), 0);
  const boundsArea = (bounds.maxX - bounds.minX + 1) * (bounds.maxY - bounds.minY + 1);
  const fillRatio = boundsArea > 0 ? foregroundPixels / boundsArea : 0;
  const touchesEdge =
    bounds.minX === 0 ||
    bounds.minY === 0 ||
    bounds.maxX === mask.width - 1 ||
    bounds.maxY === mask.height - 1;

  const warnings: string[] = [];
  if (fillRatio < 0.45) warnings.push("dirty_mask_crop");
  if (touchesEdge) warnings.push("mask_crop_touches_edge");
  if (foregroundPixels < 24) warnings.push("mask_foreground_too_small");

  return {
    ok: warnings.length === 0,
    foregroundPixels,
    boundsArea,
    fillRatio: Number(fillRatio.toFixed(4)),
    touchesEdge,
    warnings,
  };
}

function colorSaturation(r: number, g: number, b: number): number {
  const max = Math.max(r, g, b);
  const min = Math.min(r, g, b);
  return max === 0 ? 0 : (max - min) / max;
}

export function isSpecularHighlightPixel(
  r: number,
  g: number,
  b: number,
  alpha: number
): boolean {
  if (alpha <= 0) return false;
  const max = Math.max(r, g, b);
  const min = Math.min(r, g, b);
  return max >= 245 && min >= 225 && colorSaturation(r, g, b) <= 0.12;
}

function sampleReplacementColor(
  imageData: ImageData,
  x: number,
  y: number,
  radius: number
): [number, number, number] | null {
  let totalWeight = 0;
  let r = 0;
  let g = 0;
  let b = 0;

  for (let offsetY = -radius; offsetY <= radius; offsetY++) {
    for (let offsetX = -radius; offsetX <= radius; offsetX++) {
      if (offsetX === 0 && offsetY === 0) continue;
      const sampleX = x + offsetX;
      const sampleY = y + offsetY;
      if (
        sampleX < 0 ||
        sampleY < 0 ||
        sampleX >= imageData.width ||
        sampleY >= imageData.height
      ) {
        continue;
      }

      const offset = (sampleY * imageData.width + sampleX) * 4;
      const alpha = imageData.data[offset + 3] ?? 0;
      if (alpha < 32) continue;

      const sampleR = imageData.data[offset] ?? 0;
      const sampleG = imageData.data[offset + 1] ?? 0;
      const sampleB = imageData.data[offset + 2] ?? 0;
      if (isSpecularHighlightPixel(sampleR, sampleG, sampleB, alpha)) continue;

      const distance = Math.hypot(offsetX, offsetY);
      const weight = distance === 0 ? 1 : 1 / distance;
      totalWeight += weight;
      r += sampleR * weight;
      g += sampleG * weight;
      b += sampleB * weight;
    }
  }

  if (totalWeight <= 0) return null;
  return [
    Math.round(r / totalWeight),
    Math.round(g / totalWeight),
    Math.round(b / totalWeight),
  ];
}

export function repairSpecularHighlights(
  imageData: ImageData,
  searchRadius: number = DEFAULT_HIGHLIGHT_SEARCH_RADIUS
): TextureHighlightRepairSummary {
  const source = new Uint8ClampedArray(imageData.data);
  let highlightPixels = 0;
  let repairedPixels = 0;

  for (let y = 0; y < imageData.height; y++) {
    for (let x = 0; x < imageData.width; x++) {
      const offset = (y * imageData.width + x) * 4;
      const alpha = source[offset + 3] ?? 0;
      const originalR = source[offset] ?? 0;
      const originalG = source[offset + 1] ?? 0;
      const originalB = source[offset + 2] ?? 0;
      if (!isSpecularHighlightPixel(originalR, originalG, originalB, alpha)) continue;

      highlightPixels++;
      const replacement = sampleReplacementColor(
        { ...imageData, data: source },
        x,
        y,
        Math.max(1, Math.floor(searchRadius))
      );

      if (replacement) {
        imageData.data[offset] = Math.round(originalR * 0.35 + replacement[0] * 0.65);
        imageData.data[offset + 1] = Math.round(originalG * 0.35 + replacement[1] * 0.65);
        imageData.data[offset + 2] = Math.round(originalB * 0.35 + replacement[2] * 0.65);
        repairedPixels++;
      } else {
        imageData.data[offset] = Math.round(originalR * 0.85);
        imageData.data[offset + 1] = Math.round(originalG * 0.85);
        imageData.data[offset + 2] = Math.round(originalB * 0.85);
      }
    }
  }

  const foregroundPixels = Array.from(source).filter((_, index) => index % 4 === 3 && source[index] > 0)
    .length;

  return {
    strategy: "repair",
    highlightPixels,
    repairedPixels,
    highlightRatio:
      foregroundPixels > 0 ? Number((highlightPixels / foregroundPixels).toFixed(4)) : 0,
  };
}

export function inspectSpecularHighlights(
  imageData: ImageData
): TextureHighlightRepairSummary {
  let foregroundPixels = 0;
  let highlightPixels = 0;

  for (let offset = 0; offset < imageData.data.length; offset += 4) {
    const alpha = imageData.data[offset + 3] ?? 0;
    if (alpha <= 0) continue;
    foregroundPixels++;
    if (
      isSpecularHighlightPixel(
        imageData.data[offset] ?? 0,
        imageData.data[offset + 1] ?? 0,
        imageData.data[offset + 2] ?? 0,
        alpha
      )
    ) {
      highlightPixels++;
    }
  }

  return {
    strategy: "preserve",
    highlightPixels,
    repairedPixels: 0,
    highlightRatio:
      foregroundPixels > 0 ? Number((highlightPixels / foregroundPixels).toFixed(4)) : 0,
  };
}

export async function extractTextureFromMaskDetailed(
  image: CanvasImageSource,
  imageWidth: number,
  imageHeight: number,
  mask: NailMask,
  maxTextureSize: number = MAX_TEXTURE_SIZE,
  featherRadius: number = DEFAULT_FEATHER_RADIUS,
  highlightStrategy: "preserve" | "repair" = "preserve"
): Promise<ExtractedMaskTexture> {
  const quality = summarizeMaskExtractionQuality(mask);
  const bounds = findMaskBounds(mask, Boolean(mask.coverageAlpha));
  if (!bounds) {
    throw new Error("mask_has_no_foreground_pixels");
  }

  const scaleX = imageWidth / mask.width;
  const scaleY = imageHeight / mask.height;
  const sourceW = Math.max(1, Math.ceil((bounds.maxX - bounds.minX + 1) * scaleX));
  const sourceH = Math.max(1, Math.ceil((bounds.maxY - bounds.minY + 1) * scaleY));

  const outputScale = Math.min(1, maxTextureSize / Math.max(sourceW, sourceH));
  const outputWidth = Math.max(1, Math.round(sourceW * outputScale));
  const outputHeight = Math.max(1, Math.round(sourceH * outputScale));

  const canvas = new OffscreenCanvas(outputWidth, outputHeight);
  const ctx = canvas.getContext("2d");
  if (!ctx) {
    throw new Error("offscreen_canvas_2d_unavailable");
  }

  const alphaMask = buildFeatheredAlphaMask(mask, featherRadius);
  // alpha 一律经「栅格 → 双线性缩放」重建：此前非覆盖率分支按最近邻取样，
  // 二值 mask 的阶梯会在纹理域被放大成可见锯齿（模型/降级/手选路径都中招）。
  const gridWidth = bounds.maxX - bounds.minX + 1;
  const gridHeight = bounds.maxY - bounds.minY + 1;
  const grid = new OffscreenCanvas(gridWidth, gridHeight);
  const gridContext = grid.getContext("2d");
  if (!gridContext) throw new Error("offscreen_canvas_2d_unavailable");
  const pixels = new ImageData(new Uint8ClampedArray(gridWidth * gridHeight * 4), gridWidth, gridHeight);
  for (let y = 0; y < gridHeight; y++) {
    for (let x = 0; x < gridWidth; x++) {
      const offset = (y * gridWidth + x) * 4;
      pixels.data[offset] = pixels.data[offset + 1] = pixels.data[offset + 2] = 255;
      pixels.data[offset + 3] = alphaMask[(bounds.minY + y) * mask.width + bounds.minX + x];
    }
  }
  gridContext.putImageData(pixels, 0, 0);
  ctx.imageSmoothingEnabled = true;
  ctx.imageSmoothingQuality = "high";
  ctx.drawImage(grid, 0, 0, outputWidth, outputHeight);
  const coverage = ctx.getImageData(0, 0, outputWidth, outputHeight);
  // 只修正实际放大的覆盖率侧缘，避免给原尺寸轮廓加上第二层羽化。
  const isUpscaled = outputWidth >= gridWidth && outputHeight >= gridHeight &&
    (outputWidth > gridWidth || outputHeight > gridHeight);
  const principalAngle = isUpscaled ? estimateMaskPrincipalAngle(mask) : null;
  if (principalAngle !== null) {
    const original = new Uint8ClampedArray(outputWidth * outputHeight);
    for (let index = 0; index < original.length; index += 1) {
      original[index] = coverage.data[index * 4 + 3];
    }
    const proposed = smoothAlphaBoundary(tightenAlphaRamp(original), outputWidth, outputHeight);
    const refined = original.slice();
    const axisX = Math.sin(principalAngle);
    const axisY = -Math.cos(principalAngle);
    let start = Infinity;
    let stop = -Infinity;
    for (let y = bounds.minY; y <= bounds.maxY; y += 1) {
      for (let x = bounds.minX; x <= bounds.maxX; x += 1) {
        if (!mask.data[y * mask.width + x]) continue;
        const along = x * axisX + y * axisY;
        start = Math.min(start, along);
        stop = Math.max(stop, along);
      }
    }
    for (let y = 0; y < outputHeight; y += 1) {
      for (let x = 0; x < outputWidth; x += 1) {
        const i = y * outputWidth + x;
        const alpha = original[i];
        if (alpha <= 32 || alpha >= 223) continue;
        const sx = bounds.minX + (x + 0.5) * gridWidth / outputWidth - 0.5;
        const sy = bounds.minY + (y + 0.5) * gridHeight / outputHeight - 0.5;
        const t = (sx * axisX + sy * axisY - start) / (stop - start);
        // 两端保持原覆盖率，避免侧缘修正削掉甲根或甲尖。
        const amount = Math.min(1, Math.max(0, (Math.min(t, 1 - t) - 0.35) / 0.05));
        if (!(amount > 0)) continue;
        let low = alpha < 128 ? 1 : 128;
        let high = alpha < 128 ? alpha : 254;
        const neighbors = [];
        if (x > 0) neighbors.push(i - 1);
        if (x + 1 < outputWidth) neighbors.push(i + 1);
        if (y > 0) neighbors.push(i - outputWidth);
        if (y + 1 < outputHeight) neighbors.push(i + outputWidth);
        // 逐处核对四邻接，保留已存在的陡边且不新增强跳变。
        for (const j of neighbors) {
          const limit = Math.max(75, Math.abs(alpha - original[j]));
          low = Math.max(low, refined[j] - limit);
          high = Math.min(high, refined[j] + limit);
        }
        const requested = Math.round(alpha + amount * (proposed[i] - alpha));
        refined[i] = Math.max(low, Math.min(high, requested));
      }
    }
    for (let index = 0; index < refined.length; index += 1) {
      coverage.data[index * 4 + 3] = refined[index];
    }
  }
  ctx.clearRect(0, 0, outputWidth, outputHeight);
  ctx.drawImage(image, bounds.minX * scaleX, bounds.minY * scaleY,
    gridWidth * scaleX, gridHeight * scaleY, 0, 0, outputWidth, outputHeight);
  const imageData = ctx.getImageData(0, 0, outputWidth, outputHeight);
  for (let offset = 3; offset < imageData.data.length; offset += 4) {
    imageData.data[offset] = Math.round(imageData.data[offset] * coverage.data[offset] / 255);
  }
  grid.width = grid.height = 1;

  const highlightRepair =
    highlightStrategy === "repair"
      ? repairSpecularHighlights(imageData)
      : inspectSpecularHighlights(imageData);
  ctx.putImageData(imageData, 0, 0);
  return {
    texture: await createImageBitmap(canvas),
    diagnostics: {
      quality,
      highlightRepair,
    },
  };
}

export async function extractTextureFromMask(
  image: CanvasImageSource,
  imageWidth: number,
  imageHeight: number,
  mask: NailMask,
  maxTextureSize: number = MAX_TEXTURE_SIZE,
  featherRadius: number = DEFAULT_FEATHER_RADIUS,
  highlightStrategy: "preserve" | "repair" = "preserve"
): Promise<ImageBitmap> {
  const extracted = await extractTextureFromMaskDetailed(
    image,
    imageWidth,
    imageHeight,
    mask,
    maxTextureSize,
    featherRadius,
    highlightStrategy
  );
  return extracted.texture;
}

export interface NormalizedNailTextureOptions {
  /**
   * 参考甲面横轴角（弧度，如候选的 region.angle）：
   * 为掩膜主轴补全甲尖方向（消 180° 歧义），主轴不可用时整体兜底。
   */
  referenceAngle?: number | null;
  /** 模型PCA只给半转主轴；手部关键点或人工确认才提供有向参考。 */
  referenceIsDirected?: boolean;
  maxTextureSize?: number;
  featherRadius?: number;
  highlightStrategy?: "preserve" | "repair";
}

interface RgbaPlane {
  width: number;
  height: number;
  data: Uint8ClampedArray;
}

async function bitmapToRgbaPlane(bitmap: ImageBitmap): Promise<RgbaPlane> {
  const canvas = new OffscreenCanvas(bitmap.width, bitmap.height);
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("offscreen_canvas_2d_unavailable");
  ctx.drawImage(bitmap, 0, 0, bitmap.width, bitmap.height, 0, 0, bitmap.width, bitmap.height);
  const imageData = ctx.getImageData(0, 0, bitmap.width, bitmap.height);
  return { width: imageData.width, height: imageData.height, data: imageData.data };
}

async function rgbaPlaneToBitmap(plane: RgbaPlane): Promise<ImageBitmap> {
  const canvas = new OffscreenCanvas(plane.width, plane.height);
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("offscreen_canvas_2d_unavailable");
  ctx.putImageData(new ImageData(new Uint8ClampedArray(plane.data), plane.width, plane.height), 0, 0);
  return createImageBitmap(canvas);
}

/**
 * alpha 加权双线性旋转：把内容旋转 `appliedRadians`（画布坐标，+y 向下）。
 * 颜色按覆盖 alpha 预累加再除回，避免透明邻域造成的边缘发灰。
 */
function rotateRgbaPlane(src: RgbaPlane, appliedRadians: number): RgbaPlane {
  const cos = Math.cos(appliedRadians);
  const sin = Math.sin(appliedRadians);
  const outWidth = Math.max(1, Math.ceil(Math.abs(src.width * cos) + Math.abs(src.height * sin)));
  const outHeight = Math.max(1, Math.ceil(Math.abs(src.width * sin) + Math.abs(src.height * cos)));
  const data = new Uint8ClampedArray(outWidth * outHeight * 4);

  for (let y = 0; y < outHeight; y++) {
    const dy = y + 0.5 - outHeight / 2;
    for (let x = 0; x < outWidth; x++) {
      const dx = x + 0.5 - outWidth / 2;
      // 逆向映射：dst = R(A)·src ⇒ src = R(-A)·dst
      const sx = cos * dx + sin * dy - 0.5 + src.width / 2;
      const sy = -sin * dx + cos * dy - 0.5 + src.height / 2;

      const x0 = Math.floor(sx);
      const y0 = Math.floor(sy);
      const fx = sx - x0;
      const fy = sy - y0;

      let r = 0;
      let g = 0;
      let b = 0;
      let a = 0;
      for (let oy = 0; oy <= 1; oy++) {
        for (let ox = 0; ox <= 1; ox++) {
          const weight =
            (ox === 0 ? 1 - fx : fx) * (oy === 0 ? 1 - fy : fy);
          if (weight <= 0) continue;
          const px = x0 + ox;
          const py = y0 + oy;
          if (px < 0 || py < 0 || px >= src.width || py >= src.height) continue;
          const offset = (py * src.width + px) * 4;
          const alpha = (src.data[offset + 3] ?? 0) / 255;
          const covered = weight * alpha;
          r += (src.data[offset] ?? 0) * covered;
          g += (src.data[offset + 1] ?? 0) * covered;
          b += (src.data[offset + 2] ?? 0) * covered;
          a += (src.data[offset + 3] ?? 0) * weight;
        }
      }
      const outOffset = (y * outWidth + x) * 4;
      if (a <= 0) continue;
      const colorWeight = a / 255;
      data[outOffset] = Math.round(r / colorWeight);
      data[outOffset + 1] = Math.round(g / colorWeight);
      data[outOffset + 2] = Math.round(b / colorWeight);
      data[outOffset + 3] = Math.round(Math.min(255, a));
    }
  }

  return { width: outWidth, height: outHeight, data };
}

function cropRgbaPlaneToAlphaBounds(src: RgbaPlane, pad: number): RgbaPlane | null {
  let minX = src.width;
  let minY = src.height;
  let maxX = -1;
  let maxY = -1;
  for (let y = 0; y < src.height; y++) {
    for (let x = 0; x < src.width; x++) {
      if ((src.data[(y * src.width + x) * 4 + 3] ?? 0) <= 0) continue;
      if (x < minX) minX = x;
      if (y < minY) minY = y;
      if (x > maxX) maxX = x;
      if (y > maxY) maxY = y;
    }
  }
  if (maxX < minX || maxY < minY) return null;

  const x0 = Math.max(0, minX - pad);
  const y0 = Math.max(0, minY - pad);
  const x1 = Math.min(src.width - 1, maxX + pad);
  const y1 = Math.min(src.height - 1, maxY + pad);
  const width = x1 - x0 + 1;
  const height = y1 - y0 + 1;
  const data = new Uint8ClampedArray(width * height * 4);
  for (let y = 0; y < height; y++) {
    const sourceRow = ((y0 + y) * src.width + x0) * 4;
    data.set(src.data.subarray(sourceRow, sourceRow + width * 4), y * width * 4);
  }
  return { width, height, data };
}

/** 面积平均降采样（alpha 加权），用于旋转后的紧致裁剪超出尺寸上限时封顶。 */
function downscaleRgbaPlane(src: RgbaPlane, targetWidth: number, targetHeight: number): RgbaPlane {
  const data = new Uint8ClampedArray(targetWidth * targetHeight * 4);
  for (let y = 0; y < targetHeight; y++) {
    const yStart = Math.floor((y * src.height) / targetHeight);
    const yEnd = Math.max(yStart + 1, Math.floor(((y + 1) * src.height) / targetHeight));
    for (let x = 0; x < targetWidth; x++) {
      const xStart = Math.floor((x * src.width) / targetWidth);
      const xEnd = Math.max(xStart + 1, Math.floor(((x + 1) * src.width) / targetWidth));
      let r = 0;
      let g = 0;
      let b = 0;
      let a = 0;
      let weightSum = 0;
      for (let sy = yStart; sy < Math.min(yEnd, src.height); sy++) {
        for (let sx = xStart; sx < Math.min(xEnd, src.width); sx++) {
          const offset = (sy * src.width + sx) * 4;
          const alpha = (src.data[offset + 3] ?? 0) / 255;
          r += (src.data[offset] ?? 0) * alpha;
          g += (src.data[offset + 1] ?? 0) * alpha;
          b += (src.data[offset + 2] ?? 0) * alpha;
          a += src.data[offset + 3] ?? 0;
          weightSum += alpha;
        }
      }
      const outOffset = (y * targetWidth + x) * 4;
      if (weightSum <= 0) continue;
      data[outOffset] = Math.round(r / weightSum);
      data[outOffset + 1] = Math.round(g / weightSum);
      data[outOffset + 2] = Math.round(b / weightSum);
      data[outOffset + 3] = Math.round(Math.min(255, a / Math.max(1, (xEnd - xStart) * (yEnd - yStart))));
    }
  }
  return { width: targetWidth, height: targetHeight, data };
}

/**
 * 归一化纹理提取：在既有掩膜提取之上，把甲面旋转摆正（甲尖朝上）、
 * 紧致裁剪到 alpha 内容（甲面充满位图），使输出满足实时渲染
 * `drawCurvedTexture` 的「正立、甲尖朝上、甲面充满」假设。
 * 方向由掩膜主轴描述，甲尖方向由 `referenceAngle` 消歧；详见
 * `resolveMaskTextureRotation`。
 */
export async function extractNormalizedNailTexture(
  image: CanvasImageSource,
  imageWidth: number,
  imageHeight: number,
  mask: NailMask,
  options: NormalizedNailTextureOptions = {}
): Promise<ExtractedMaskTexture> {
  const maxTextureSize = options.maxTextureSize ?? MAX_TEXTURE_SIZE;
  const base = await extractTextureFromMaskDetailed(
    image,
    imageWidth,
    imageHeight,
    mask,
    maxTextureSize,
    options.featherRadius ?? DEFAULT_FEATHER_RADIUS,
    options.highlightStrategy ?? "preserve"
  );
  const resolved = resolveMaskTextureRotation(mask, options.referenceAngle ?? null, options.referenceIsDirected ?? true);

  let plane = await bitmapToRgbaPlane(base.texture);
  const applied = -resolved.rotation;
  if (Math.abs(applied) > 1e-9) {
    plane = rotateRgbaPlane(plane, applied);
  }
  plane = cropRgbaPlaneToAlphaBounds(plane, NORMALIZATION_EDGE_PAD) ?? plane;

  const longest = Math.max(plane.width, plane.height);
  if (longest > maxTextureSize) {
    const scale = maxTextureSize / longest;
    plane = downscaleRgbaPlane(
      plane,
      Math.max(1, Math.round(plane.width * scale)),
      Math.max(1, Math.round(plane.height * scale))
    );
  }

  const texture = await rgbaPlaneToBitmap(plane);
  return {
    texture,
    diagnostics: {
      ...base.diagnostics,
      normalization: {
        rotationRadians: resolved.rotation,
        source: resolved.source,
        warnings: resolved.warnings,
      },
    },
  };
}
