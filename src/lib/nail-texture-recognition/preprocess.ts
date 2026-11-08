import type { ImagePixels } from "../nail-image-detection.ts";

export interface NailTexturePreprocessResult {
  inputSize: number;
  originalWidth: number;
  originalHeight: number;
  scaleX: number;
  scaleY: number;
  resizeScale?: number;
  resizedWidth?: number;
  resizedHeight?: number;
  padLeft?: number;
  padTop?: number;
  tensorData: Float32Array;
  tensorShape: [1, 3, number, number];
}

/**
 * cvRound：saturate_cast<short>(float) 的 SSE cvtss2si 语义（round-half-to-even）。
 */
function cvRoundHalfEven(value: number): number {
  const floor = Math.floor(value);
  const fraction = value - floor;
  if (fraction > 0.5) return floor + 1;
  if (fraction < 0.5) return floor;
  return floor % 2 === 0 ? floor : floor + 1;
}

/**
 * cv2.resize INTER_LINEAR（8U C3）的逐位复刻（对齐 OpenCV 5.x resize.cpp 通用路径）。
 *
 * 关键语义（与直觉双线性不同，均已按源码复刻）：
 * - scale = 1.0/(dst/src) 双重 double 除法；fx = (float)((dx+0.5)·scale − 0.5)，
 *   且 fx -= sx 与 1.f − fx 都在 float32 内计算。
 * - 两个系数独立 cvRound（half-even），a0+a1 可为 2047/2048/2049。
 * - 右边界列（sx ≥ srcW−1）：fx=0、sx=srcW−1，主循环停在 xmax，尾部 D = S[xofs]·2048
 *   纯复制末像素；左边界（sx<0）：fx=0、sx=0，仍在主循环以 [2048,0] 系数复制首像素。
 * - 垂直合成：out = ((b0·(S0>>4))>>16 + (b1·(S1>>4))>>16 + 2) >> 2（uint8 饱和），
 *   其中 S0/S1 为水平 int 缓冲（>>4 为截断）。
 * - scale 恰为 2 时 cv2 会改走 INTER_AREA 快路径，本函数未实现该分支；
 *   生产 letterbox 尺度为 1.5625，恒走通用路径。
 */
export function resizeLinearC3Cv2BitExact(
  src: Uint8Array,
  srcWidth: number,
  srcHeight: number,
  dstWidth: number,
  dstHeight: number
): Uint8Array {
  const invScaleX = dstWidth / srcWidth;
  const invScaleY = dstHeight / srcHeight;
  const scaleX = 1 / invScaleX;
  const scaleY = 1 / invScaleY;

  const xofs = new Int32Array(dstWidth * 3);
  const ialpha = new Int32Array(dstWidth * 3 * 2);
  let xmax = dstWidth * 3;
  for (let dx = 0; dx < dstWidth; dx++) {
    let fx = Math.fround((dx + 0.5) * scaleX - 0.5);
    let sx = Math.floor(fx);
    fx = Math.fround(fx - sx);
    if (sx < 0) {
      fx = 0;
      sx = 0;
    }
    if (sx >= srcWidth - 1) {
      if (dx * 3 < xmax) xmax = dx * 3;
      fx = 0;
      sx = srcWidth - 1;
    }
    const c0 = Math.fround(1 - fx);
    for (let channel = 0; channel < 3; channel++) {
      xofs[dx * 3 + channel] = sx * 3 + channel;
      ialpha[(dx * 3 + channel) * 2] = cvRoundHalfEven(Math.fround(c0 * 2048));
      ialpha[(dx * 3 + channel) * 2 + 1] = cvRoundHalfEven(Math.fround(fx * 2048));
    }
  }

  const yofs = new Int32Array(dstHeight);
  const ibeta = new Int32Array(dstHeight * 2);
  for (let dy = 0; dy < dstHeight; dy++) {
    // OpenCV 的垂直系数初始化无边界钳制：sy 可为 −1 或 srcH−1，fy 恒回绕到 [0,1)；
    // 越界行在行 gather 时 clip（两侧可为同一行），此时 [1−fy, fy] 拆分取整与
    // [2048, 0] 合并取整结果不同（水平方向因 xmax 尾部机制才有钳制）。
    let fy = Math.fround((dy + 0.5) * scaleY - 0.5);
    const sy = Math.floor(fy);
    fy = Math.fround(fy - sy);
    yofs[dy] = sy;
    const c0 = Math.fround(1 - fy);
    ibeta[dy * 2] = cvRoundHalfEven(Math.fround(c0 * 2048));
    ibeta[dy * 2 + 1] = cvRoundHalfEven(Math.fround(fy * 2048));
  }

  const out = new Uint8Array(dstWidth * 3 * dstHeight);
  const rowBuffers = [
    new Int32Array(dstWidth * 3),
    new Int32Array(dstWidth * 3),
  ];
  const rowSourceIndex = [0, 0];
  for (let dy = 0; dy < dstHeight; dy++) {
    const sy0 = yofs[dy];
    rowSourceIndex[0] =
      Math.min(Math.max(sy0, 0), srcHeight - 1) * srcWidth * 3;
    rowSourceIndex[1] =
      Math.min(Math.max(sy0 + 1, 0), srcHeight - 1) * srcWidth * 3;
    for (let row = 0; row < 2; row++) {
      const sourceRow = rowSourceIndex[row];
      const buffer = rowBuffers[row];
      for (let dx = 0; dx < xmax; dx++) {
        const sx = xofs[dx];
        buffer[dx] = src[sourceRow + sx] * ialpha[dx * 2] + src[sourceRow + sx + 3] * ialpha[dx * 2 + 1];
      }
      for (let dx = xmax; dx < dstWidth * 3; dx++) {
        buffer[dx] = src[sourceRow + xofs[dx]] * 2048;
      }
    }
    const b0 = ibeta[dy * 2];
    const b1 = ibeta[dy * 2 + 1];
    const row0 = rowBuffers[0];
    const row1 = rowBuffers[1];
    const outRow = dy * dstWidth * 3;
    for (let dx = 0; dx < dstWidth * 3; dx++) {
      const value =
        (((b0 * (row0[dx] >> 4)) >> 16) + ((b1 * (row1[dx] >> 4)) >> 16) + 2) >> 2;
      out[outRow + dx] = value < 0 ? 0 : value > 255 ? 255 : value;
    }
  }
  return out;
}

export function preprocessNailTextureImage(
  source: ImagePixels,
  inputSize: number
): NailTexturePreprocessResult {
  if (source.width < 1 || source.height < 1) {
    throw new Error("invalid_nail_texture_source_dimensions");
  }
  if (!Number.isInteger(inputSize) || inputSize < 1) {
    throw new Error("invalid_nail_texture_input_size");
  }

  const tensorData = new Float32Array(3 * inputSize * inputSize);
  const resizeScale = Math.min(inputSize / source.width, inputSize / source.height);
  const resizedWidth = Math.max(1, Math.min(inputSize, Math.round(source.width * resizeScale)));
  const resizedHeight = Math.max(1, Math.min(inputSize, Math.round(source.height * resizeScale)));
  const padLeft = Math.floor((inputSize - resizedWidth) / 2);
  const padTop = Math.floor((inputSize - resizedHeight) / 2);
  const scaleX = 1 / resizeScale;
  const scaleY = 1 / resizeScale;
  const channelArea = inputSize * inputSize;
  const paddingValue = 114 / 255;
  tensorData.fill(paddingValue);

  // cv2 INTER_LINEAR 8U 逐位复刻的 letterbox 重采样（与训练/服务端 cv2.resize 一致），
  // 之后再按 uint8 /255 写入张量（与服务端 uint8 图像链路一致）。
  const packedRgb = new Uint8Array(source.width * source.height * 3);
  for (let index = 0; index < source.width * source.height; index++) {
    const sourceOffset = index * 4;
    packedRgb[index * 3] = Number(source.data[sourceOffset]) || 0;
    packedRgb[index * 3 + 1] = Number(source.data[sourceOffset + 1]) || 0;
    packedRgb[index * 3 + 2] = Number(source.data[sourceOffset + 2]) || 0;
  }
  const resized = resizeLinearC3Cv2BitExact(
    packedRgb,
    source.width,
    source.height,
    resizedWidth,
    resizedHeight
  );
  for (let channel = 0; channel < 3; channel++) {
    const channelBase = channel * channelArea;
    for (let y = 0; y < resizedHeight; y++) {
      const sourceRow = y * resizedWidth * 3 + channel;
      const targetRow = channelBase + (padTop + y) * inputSize + padLeft;
      for (let x = 0; x < resizedWidth; x++) {
        tensorData[targetRow + x] = Math.fround(resized[sourceRow + x * 3] / 255);
      }
    }
  }

  return {
    inputSize,
    originalWidth: source.width,
    originalHeight: source.height,
    scaleX,
    scaleY,
    resizeScale,
    resizedWidth,
    resizedHeight,
    padLeft,
    padTop,
    tensorData,
    tensorShape: [1, 3, inputSize, inputSize],
  };
}
