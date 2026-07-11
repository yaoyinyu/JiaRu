import type { NailMask } from "./types.ts";

const MAX_TEXTURE_SIZE = 256;
const DEFAULT_FEATHER_RADIUS = 2;
const DEFAULT_HIGHLIGHT_SEARCH_RADIUS = 3;

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

export interface TextureExtractionDiagnostics {
  quality: MaskExtractionQualitySummary;
  highlightRepair: TextureHighlightRepairSummary;
}

export interface ExtractedMaskTexture {
  texture: ImageBitmap;
  diagnostics: TextureExtractionDiagnostics;
}

export function findMaskBounds(mask: NailMask): MaskBounds | null {
  let minX = mask.width;
  let minY = mask.height;
  let maxX = -1;
  let maxY = -1;

  for (let y = 0; y < mask.height; y++) {
    for (let x = 0; x < mask.width; x++) {
      if (!mask.data[y * mask.width + x]) continue;
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

  return alpha;
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
  const bounds = findMaskBounds(mask);
  if (!bounds) {
    throw new Error("mask_has_no_foreground_pixels");
  }

  const scaleX = imageWidth / mask.width;
  const scaleY = imageHeight / mask.height;
  const sourceX = Math.max(0, Math.floor(bounds.minX * scaleX));
  const sourceY = Math.max(0, Math.floor(bounds.minY * scaleY));
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

  ctx.drawImage(image, sourceX, sourceY, sourceW, sourceH, 0, 0, outputWidth, outputHeight);
  const imageData = ctx.getImageData(0, 0, outputWidth, outputHeight);
  const alphaMask = buildFeatheredAlphaMask(mask, featherRadius);

  for (let y = 0; y < outputHeight; y++) {
    const maskY = Math.min(
      mask.height - 1,
      bounds.minY + Math.floor((y / outputHeight) * (bounds.maxY - bounds.minY + 1))
    );
    for (let x = 0; x < outputWidth; x++) {
      const maskX = Math.min(
        mask.width - 1,
        bounds.minX + Math.floor((x / outputWidth) * (bounds.maxX - bounds.minX + 1))
      );
      imageData.data[(y * outputWidth + x) * 4 + 3] =
        alphaMask[maskY * mask.width + maskX] ?? 0;
    }
  }

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
