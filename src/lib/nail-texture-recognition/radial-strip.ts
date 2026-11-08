/**
 * 径向条带构建的浏览器宿主实现（对齐 model/training/native-radial-strip-refiner.build_strip）。
 *
 * 数值口径：theta/采样坐标在 float64 计算，乘加结果 cast float32；先对 [0,1] RGB 与
 * 粗 mask 通道做双线性插值，再对前 3 通道做 ImageNet 归一化；第 5 通道为 offset/64。
 * 输出布局为 channel-major [5][angle][radial] 的 Float32Array（可直接喂 [1,5,2048,129] 输入）。
 */

export interface RadialStripSource {
  width: number;
  height: number;
  /** RGBA 像素（ImageData.data 兼容）。 */
  data: ArrayLike<number>;
}

export interface RadialStripRoi {
  /** ROI 左上角在原图中的坐标。 */
  x0: number;
  y0: number;
  /** ROI 宽高（正方形 side）。 */
  side: number;
}

const IMAGE_NET_MEAN = [0.485, 0.456, 0.406].map(Math.fround);
const IMAGE_NET_STD = [0.229, 0.224, 0.225].map(Math.fround);

/**
 * 构建 5 通道径向条带：RGB(ImageNet 归一化) + 粗 mask + 径向位置。
 * coarse 为 ROI 局部二值 mask（side×side，0/1）；center 为 ROI 局部 float64 坐标。
 */
export function buildRadialStrip(
  source: RadialStripSource,
  roi: RadialStripRoi,
  coarse: Uint8Array,
  centerX: number,
  centerY: number,
  radii: Float32Array,
  angularSamples: number
): Float32Array {
  if (radii.length !== angularSamples) {
    throw new Error("radial_strip_radii_length_mismatch");
  }
  if (coarse.length !== roi.side * roi.side) {
    throw new Error("radial_strip_coarse_shape_mismatch");
  }
  const radialSamples = 129;
  const output = new Float32Array(5 * angularSamples * radialSamples);

  // theta = (arange(N, float64) + .5) * (2π/N)，float64。
  const twoPi = 2 * Math.PI;
  const thetaStep = twoPi / angularSamples;

  // values = RGB/255 与 coarse 拼成 4 通道（float32）。
  const roiWidth = roi.side;
  const roiHeight = roi.side;
  const values = new Float32Array(roiWidth * roiHeight * 4);
  for (let index = 0; index < roiWidth * roiHeight; index++) {
    const sourceX = roi.x0 + (index % roiWidth);
    const sourceY = roi.y0 + Math.floor(index / roiWidth);
    const sourceIndex = (sourceY * source.width + sourceX) * 4;
    values[index * 4] = Math.fround((Number(source.data[sourceIndex]) || 0) / 255);
    values[index * 4 + 1] = Math.fround((Number(source.data[sourceIndex + 1]) || 0) / 255);
    values[index * 4 + 2] = Math.fround((Number(source.data[sourceIndex + 2]) || 0) / 255);
    values[index * 4 + 3] = coarse[index];
  }

  for (let angle = 0; angle < angularSamples; angle++) {
    const theta = (angle + 0.5) * thetaStep;
    const cosTheta = Math.cos(theta);
    const sinTheta = Math.sin(theta);
    for (let radialIndex = 0; radialIndex < radialSamples; radialIndex++) {
      const offset = radialIndex - 64;
      // radial = max(0, radii + offset)，float32 加法。
      const radial = Math.fround(radii[angle] + offset);
      const radialClamped = radial < 0 ? 0 : radial;
      // x = centerX + cosθ·radial（double 乘加后 cast float32）。
      let x = Math.fround(centerX + cosTheta * radialClamped);
      let y = Math.fround(centerY + sinTheta * radialClamped);
      if (x < 0) x = 0;
      if (x > roiWidth - 1) x = roiWidth - 1;
      if (y < 0) y = 0;
      if (y > roiHeight - 1) y = roiHeight - 1;
      const x0 = Math.floor(x);
      const y0 = Math.floor(y);
      const x1 = Math.min(x0 + 1, roiWidth - 1);
      const y1 = Math.min(y0 + 1, roiHeight - 1);
      const wx = Math.fround(x - x0);
      const wy = Math.fround(y - y0);

      const index00 = (y0 * roiWidth + x0) * 4;
      const index01 = (y0 * roiWidth + x1) * 4;
      const index10 = (y1 * roiWidth + x0) * 4;
      const index11 = (y1 * roiWidth + x1) * 4;
      const oneMinusWx = Math.fround(1 - wx);
      const oneMinusWy = Math.fround(1 - wy);
      for (let channel = 0; channel < 4; channel++) {
        const v00 = values[index00 + channel];
        const v01 = values[index01 + channel];
        const v10 = values[index10 + channel];
        const v11 = values[index11 + channel];
        const top = Math.fround(Math.fround(v00 * oneMinusWx) + Math.fround(v01 * wx));
        const bottom = Math.fround(Math.fround(v10 * oneMinusWx) + Math.fround(v11 * wx));
        let sampled = Math.fround(Math.fround(top * oneMinusWy) + Math.fround(bottom * wy));
        if (channel < 3) {
          sampled = Math.fround(Math.fround(sampled - IMAGE_NET_MEAN[channel]) / IMAGE_NET_STD[channel]);
        }
        output[(channel * angularSamples + angle) * radialSamples + radialIndex] = sampled;
      }
      // 第 5 通道：offsets/64（2 的幂除法，精确）。
      output[(4 * angularSamples + angle) * radialSamples + radialIndex] = Math.fround(offset / 64);
    }
  }
  return output;
}
