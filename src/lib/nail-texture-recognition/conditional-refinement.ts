/** 实验精修接口；须经发布门后才可接入正式自动队列。 */
export const CONDITIONAL_REFINEMENT_SIZE = 384;

export type ConditionalRefinementResult =
  | { kind: "mask"; mask: Uint8Array; width: number; height: number; cropBox: readonly number[] }
  | { kind: "rejected" }
  | { kind: "execution-error"; reason: string };

/** 输入必须是已按同一方形ROI准备的384 RGB及同候选粗mask；禁止真值提示。 */
export function packConditionalRefinementInput(rgb: Uint8Array, coarseMask: Uint8Array): Float32Array {
  const pixels = CONDITIONAL_REFINEMENT_SIZE ** 2;
  if (rgb.length !== pixels * 3 || coarseMask.length !== pixels) throw new Error("条件ROI输入尺寸错误");
  const result = new Float32Array(pixels * 4);
  const means = [0.485, 0.456, 0.406];
  const deviations = [0.229, 0.224, 0.225];
  for (let i = 0; i < pixels; i++) {
    for (let channel = 0; channel < 3; channel++) result[channel * pixels + i] = (rgb[i * 3 + channel] / 255 - means[channel]) / deviations[channel];
    if (coarseMask[i] !== 0 && coarseMask[i] !== 255) throw new Error("同候选粗mask必须为二值");
    result[3 * pixels + i] = coarseMask[i] / 255;
  }
  return result;
}

/** PIL浮点BILINEAR口径：下采样扩大滤波窗，边界重归一化。 */
function weights(sourceSize: number, targetSize: number): Array<Array<[number, number]>> {
  const scale = sourceSize / targetSize;
  const filterScale = Math.max(1, scale);
  return Array.from({ length: targetSize }, (_, i) => {
    const center = (i + 0.5) * scale;
    const row: Array<[number, number]> = [];
    let total = 0;
    for (let j = Math.max(0, Math.ceil(center - filterScale - 0.5)); j < Math.min(sourceSize, Math.ceil(center + filterScale - 0.5)); j++) {
      const weight = Math.max(0, 1 - Math.abs((j + 0.5 - center) / filterScale));
      if (weight > 0) { row.push([j, weight]); total += weight; }
    }
    return row.map(([index, weight]) => [index, weight / total]);
  });
}

export function decodeConditionalRefinement(
  logits: Float32Array,
  dims: readonly number[],
  cropBox: readonly number[],
  imageSize: readonly number[],
  threshold = 0.5,
): ConditionalRefinementResult {
  const size = CONDITIONAL_REFINEMENT_SIZE;
  if (dims.length !== 4 || dims.some((v, i) => v !== [1, 1, size, size][i]) || logits.length !== size * size) return { kind: "execution-error", reason: "精修输出形状错误" };
  if (cropBox.length !== 4 || imageSize.length !== 2 || [...cropBox, ...imageSize].some(v => !Number.isSafeInteger(v)) || imageSize.some(v => v <= 0)) return { kind: "execution-error", reason: "原图坐标合同错误" };
  const [x0, y0, x1, y1] = cropBox;
  if (x0 < 0 || y0 < 0 || x1 > imageSize[0] || y1 > imageSize[1] || x1 <= x0 || y1 <= y0 || !Number.isFinite(threshold) || threshold <= 0 || threshold >= 1) return { kind: "execution-error", reason: "裁块越界或阈值错误" };
  const width = x1 - x0, height = y1 - y0;
  const wx = weights(size, width), wy = weights(size, height);
  const horizontal = new Float32Array(width * size);
  for (let y = 0; y < size; y++) {
    for (let x = 0; x < width; x++) {
      let value = 0;
      for (const [sx, weight] of wx[x]) {
        const logit = logits[y * size + sx];
        if (!Number.isFinite(logit)) return { kind: "execution-error", reason: "精修输出非有限值" };
        value += weight * Math.fround(1 / (1 + Math.exp(-logit)));
      }
      horizontal[y * width + x] = value;
    }
  }
  const mask = new Uint8Array(width * height);
  let count = 0;
  for (let y = 0; y < height; y++) for (let x = 0; x < width; x++) {
    let value = 0;
    for (const [sy, weight] of wy[y]) value += horizontal[sy * width + x] * weight;
    // Pillow F将最终概率写入float32后再阈值化；直接对JS double比较会改边界像素。
    if (Math.fround(value) >= threshold) { mask[y * width + x] = 1; count++; }
  }
  // 有效空输出永久拒绝该候选，不取旧粗mask回填；错误分支交由产品人工确认。
  return count === 0 ? { kind: "rejected" } : { kind: "mask", mask, width, height, cropBox };
}
