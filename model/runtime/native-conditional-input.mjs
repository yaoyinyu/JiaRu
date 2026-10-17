// 原尺寸四通道开发输入；正式发布身份批准前仅供隔离链路使用。
const MEAN = [0.485, 0.456, 0.406];
const DEVIATION = [0.229, 0.224, 0.225];

export function packNativeConditionalInput(rgb, coarse, width, height) {
  if (![width, height].every((n) => Number.isInteger(n) && n >= 4 && n <= 661)) {
    throw new Error("native input dimensions outside controlled domain");
  }
  const pixels = width * height;
  if (!(rgb instanceof Uint8Array) || rgb.length !== pixels * 3
      || !(coarse instanceof Uint8Array) || coarse.length !== pixels) {
    throw new Error("native RGB and same-candidate seed must be exact uint8 arrays");
  }
  for (const value of coarse) {
    if (value !== 0 && value !== 255) throw new Error("native seed must be binary 0/255");
  }
  const result = new Float32Array(4 * pixels);
  for (let i = 0; i < pixels; i++) {
    // 与权威Python一致：双精度除法、减均值、除标准差，最后一次F32存储。
    for (let channel = 0; channel < 3; channel++) {
      result[channel * pixels + i] = (rgb[i * 3 + channel] / 255 - MEAN[channel]) / DEVIATION[channel];
    }
    result[3 * pixels + i] = coarse[i] / 255;
  }
  return result;
}
