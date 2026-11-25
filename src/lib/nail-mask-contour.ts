import type { NailMask } from "./nail-texture-recognition/types.ts";

/**
 * 甲面掩膜外轮廓：把模型/精细抠图给出的掩膜还原成边界线段，
 * 供选择器按真实甲面形状绘制框选边界——椭圆只能表达长宽与角度，
 * 细长甲、侧转甲、根部收窄的甲用椭圆框会和实际纹理形状不符。
 */

/** 原图坐标下的掩膜边界线段（等于前景像素与背景像素之间的像素边）。 */
export interface MaskBoundarySegment {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
}

const segmentCache = new WeakMap<NailMask, MaskBoundarySegment[] | null>();

interface ComponentResult {
  label: Uint8Array;
  target: number;
  size: number;
}

/** 最大 4 连通域：模型掩膜可能带孤立噪点，只描主甲面。 */
function largestComponentLabels(mask: NailMask): ComponentResult | null {
  const { width, height, data } = mask;
  const label = new Uint8Array(width * height);
  const stack: number[] = [];
  let currentLabel = 0;
  let bestLabel = 0;
  let bestSize = 0;

  for (let index = 0; index < data.length; index += 1) {
    if (!data[index] || label[index]) continue;
    currentLabel += 1;
    let size = 0;
    stack.push(index);
    label[index] = currentLabel;
    while (stack.length > 0) {
      const cursor = stack.pop() as number;
      size += 1;
      const x = cursor % width;
      const y = (cursor - x) / width;
      if (x > 0 && data[cursor - 1] && !label[cursor - 1]) {
        label[cursor - 1] = currentLabel;
        stack.push(cursor - 1);
      }
      if (x + 1 < width && data[cursor + 1] && !label[cursor + 1]) {
        label[cursor + 1] = currentLabel;
        stack.push(cursor + 1);
      }
      if (y > 0 && data[cursor - width] && !label[cursor - width]) {
        label[cursor - width] = currentLabel;
        stack.push(cursor - width);
      }
      if (y + 1 < height && data[cursor + width] && !label[cursor + width]) {
        label[cursor + width] = currentLabel;
        stack.push(cursor + width);
      }
    }
    if (size > bestSize) {
      bestSize = size;
      bestLabel = currentLabel;
    }
  }

  if (bestLabel <= 0) return null;
  return { label, target: bestLabel, size: bestSize };
}

/**
 * 提取掩膜主连通域的外轮廓线段（换算到原图坐标）。
 *
 * 坐标映射与纹理提取保持同一口径：掩膜按「整图栅格」解释，掩膜像素 × (原图边长 / 掩膜边长)。
 * 提取器就是这么采样的（`extractTextureFromMaskDetailed`），框与纹理因此逐像素同形。
 */
export function maskBoundarySegments(
  mask: NailMask | null | undefined,
  imageSize: { width: number; height: number }
): MaskBoundarySegment[] | null {
  if (!mask || mask.width <= 1 || mask.height <= 1) return null;
  if (mask.data.length !== mask.width * mask.height) return null;
  if (!(imageSize.width > 0) || !(imageSize.height > 0)) return null;
  const cached = segmentCache.get(mask);
  if (cached !== undefined) return cached;

  const component = largestComponentLabels(mask);
  if (!component || component.size < 12) {
    segmentCache.set(mask, null);
    return null;
  }

  const { width, height } = mask;
  const { label, target } = component;
  const inMain = (index: number) => label[index] === target;
  const scaleX = imageSize.width / mask.width;
  const scaleY = imageSize.height / mask.height;
  const toX = (value: number) => value * scaleX;
  const toY = (value: number) => value * scaleY;
  const segments: MaskBoundarySegment[] = [];

  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      const index = y * width + x;
      if (!inMain(index)) continue;
      const top = y === 0 || !inMain(index - width);
      const bottom = y + 1 >= height || !inMain(index + width);
      const left = x === 0 || !inMain(index - 1);
      const right = x + 1 >= width || !inMain(index + 1);
      if (top) segments.push({ x1: toX(x), y1: toY(y), x2: toX(x + 1), y2: toY(y) });
      if (bottom) segments.push({ x1: toX(x), y1: toY(y + 1), x2: toX(x + 1), y2: toY(y + 1) });
      if (left) segments.push({ x1: toX(x), y1: toY(y), x2: toX(x), y2: toY(y + 1) });
      if (right) segments.push({ x1: toX(x + 1), y1: toY(y), x2: toX(x + 1), y2: toY(y + 1) });
    }
  }

  const result = segments.length > 0 ? segments : null;
  segmentCache.set(mask, result);
  return result;
}
