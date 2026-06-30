import type { NailMask } from "./types.ts";

const MAX_TEXTURE_SIZE = 256;

export interface MaskBounds {
  minX: number;
  minY: number;
  maxX: number;
  maxY: number;
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

export async function extractTextureFromMask(
  image: CanvasImageSource,
  imageWidth: number,
  imageHeight: number,
  mask: NailMask,
  maxTextureSize: number = MAX_TEXTURE_SIZE
): Promise<ImageBitmap> {
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
        mask.data[maskY * mask.width + maskX] ? 255 : 0;
    }
  }

  ctx.putImageData(imageData, 0, 0);
  return createImageBitmap(canvas);
}
