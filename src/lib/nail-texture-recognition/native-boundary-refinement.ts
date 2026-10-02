/** 实验原像素纠正合同；发布门通过前不接正式自动队列。 */
export type NativeBoundaryResult =
  | { kind: "mask"; mask: Uint8Array; width: number; height: number; cropBox: readonly number[] }
  | { kind: "rejected" }
  | { kind: "execution-error"; reason: string };

function validateBase(base: Float32Array, width: number, height: number): number {
  if (!Number.isSafeInteger(width) || !Number.isSafeInteger(height) || width < 1 || height < 1 || !Number.isSafeInteger(width * height) || base.length !== width * height) throw new Error("原像素输入尺寸错误");
  for (const value of base) if (!Number.isFinite(value) || value < 0 || value > 1) throw new Error("冻结基底概率错误");
  return width * height;
}

/** 内边缘3×3腐蚀采用ROI外零填充，再按4原像素Chebyshev半径膨胀。 */
export function nativeBoundaryBand(base: Float32Array, width: number, height: number): Uint8Array {
  const pixels = validateBase(base, width, height);
  const edge = new Uint8Array(pixels);
  for (let y = 0; y < height; y++) for (let x = 0; x < width; x++) {
    const i = y * width + x;
    if (base[i] < 0.5) continue;
    let inner = true;
    for (let dy = -1; dy <= 1 && inner; dy++) for (let dx = -1; dx <= 1; dx++) {
      const nx = x + dx, ny = y + dy;
      if (nx < 0 || ny < 0 || nx >= width || ny >= height || base[ny * width + nx] < 0.5) { inner = false; break; }
    }
    if (!inner) edge[i] = 1;
  }
  const stride = width + 1, integral = new Float64Array(stride * (height + 1));
  for (let y = 0; y < height; y++) {
    let sum = 0;
    for (let x = 0; x < width; x++) { sum += edge[y * width + x]; integral[(y + 1) * stride + x + 1] = sum + integral[y * stride + x + 1]; }
  }
  const band = new Uint8Array(pixels);
  for (let y = 0; y < height; y++) for (let x = 0; x < width; x++) {
    const x0 = Math.max(0, x - 4), x1 = Math.min(width, x + 5), y0 = Math.max(0, y - 4), y1 = Math.min(height, y + 5);
    if (integral[y1 * stride + x1] - integral[y0 * stride + x1] - integral[y1 * stride + x0] + integral[y0 * stride + x0] > 0) band[y * width + x] = 1;
  }
  return band;
}

export function packNativeBoundaryInput(rgb: Uint8Array, coarse: Uint8Array, base: Float32Array, width: number, height: number): { packed: Float32Array; band: Uint8Array } {
  const pixels = validateBase(base, width, height);
  if (rgb.length !== pixels * 3 || coarse.length !== pixels) throw new Error("原尺寸RGB/粗mask错误");
  const band = nativeBoundaryBand(base, width, height), packed = new Float32Array(6 * pixels);
  const means = [0.485, 0.456, 0.406], deviations = [0.229, 0.224, 0.225];
  for (let i = 0; i < pixels; i++) {
    for (let c = 0; c < 3; c++) packed[c * pixels + i] = (rgb[3 * i + c] / 255 - means[c]) / deviations[c];
    if (coarse[i] !== 0 && coarse[i] !== 255) throw new Error("粗mask须为二值");
    packed[3 * pixels + i] = base[i]; packed[4 * pixels + i] = coarse[i] / 255; packed[5 * pixels + i] = band[i];
  }
  return { packed, band };
}

/** 带外复制原float32位，带内双精度组合后写float32；有效空基底始终不产生新候选。 */
export function composeNativeBoundaryProbability(base: Float32Array, delta: Float32Array, width: number, height: number): Float32Array {
  const pixels = validateBase(base, width, height);
  if (delta.length !== pixels) throw new Error("原像素残差尺寸错误");
  for (const value of delta) if (!Number.isFinite(value)) throw new Error("纠正头非有限输出");
  const band = nativeBoundaryBand(base, width, height), probability = new Float32Array(base);
  for (let i = 0; i < pixels; i++) if (band[i]) {
    const p = Math.max(1e-6, Math.min(1 - 1e-6, base[i]));
    const logit = Math.max(-80, Math.min(80, Math.log(p) - Math.log1p(-p) + delta[i]));
    probability[i] = 1 / (1 + Math.exp(-logit));
  }
  return probability;
}

export function decodeNativeBoundaryDelta(base: Float32Array, delta: Float32Array, dims: readonly number[], cropBox: readonly number[], imageSize: readonly number[]): NativeBoundaryResult {
  try {
    if (cropBox.length !== 4 || imageSize.length !== 2 || [...cropBox, ...imageSize].some(v => !Number.isSafeInteger(v))) throw new Error("原图坐标错误");
    const [x0, y0, x1, y1] = cropBox, width = x1 - x0, height = y1 - y0;
    if (x0 < 0 || y0 < 0 || x1 > imageSize[0] || y1 > imageSize[1] || imageSize.some(v => v < 1) || dims.length !== 4 || dims.some((v, i) => v !== [1, 1, height, width][i])) throw new Error("原图越界或动态输出尺寸错误");
    const probability = composeNativeBoundaryProbability(base, delta, width, height), mask = new Uint8Array(probability.length);
    let count = 0;
    for (let i = 0; i < mask.length; i++) if (probability[i] >= 0.5) { mask[i] = 1; count++; }
    return count ? { kind: "mask", mask, width, height, cropBox } : { kind: "rejected" };
  } catch (error) { return { kind: "execution-error", reason: String(error) }; }
}
