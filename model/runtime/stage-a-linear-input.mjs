// 隔离的512输入路径；像素语义绑定OpenCV 5.0.0 INTER_LINEAR uint8。
// 算法依据：https://github.com/opencv/opencv/blob/5.0.0/modules/imgproc/src/resize.cpp
// 不使用Canvas缩放，不改变现有产品预处理。
function roundEven(value) {
  const lower = Math.floor(value);
  const fraction = value - lower;
  return fraction < 0.5 ? lower : fraction > 0.5 ? lower + 1 : lower + (lower % 2);
}

function coefficients(sourceSize, targetSize, horizontal) {
  const offsets = new Int32Array(targetSize);
  const weights = new Int32Array(targetSize * 2);
  const scale = 1 / (targetSize / sourceSize);
  for (let target = 0; target < targetSize; target++) {
    const coordinate = Math.fround((target + 0.5) * scale - 0.5);
    let source = Math.floor(coordinate);
    let fraction = Math.fround(coordinate - source);
    if (horizontal && (source < 0 || source >= sourceSize - 1)) {
      source = Math.max(0, Math.min(sourceSize - 1, source));
      fraction = 0;
    }
    offsets[target] = source;
    weights[target * 2] = roundEven(Math.fround(1 - fraction) * 2048);
    weights[target * 2 + 1] = roundEven(fraction * 2048);
  }
  return { offsets, weights };
}

export function packStageALinearInput(rgb, width, height) {
  if (!Number.isInteger(width) || !Number.isInteger(height) ||
      width < 1 || height < 1 || width > 8192 || height > 8192 ||
      !(rgb instanceof Uint8Array) || rgb.length !== width * height * 3) {
    throw new TypeError('Stage A requires exact RGB uint8 and integer dimensions in [1,8192]');
  }
  const scale = Math.min(512 / width, 512 / height);
  const resizedWidth = roundEven(width * scale);
  const resizedHeight = roundEven(height * scale);
  if (resizedWidth < 1 || resizedHeight < 1) throw new RangeError('Empty resized side');
  const padLeft = roundEven((512 - resizedWidth) / 2 - 0.1);
  const padTop = roundEven((512 - resizedHeight) / 2 - 0.1);
  const letterbox = new Uint8Array(512 * 512 * 3).fill(114);
  const half = width === resizedWidth * 2 && height === resizedHeight * 2;
  const x = coefficients(width, resizedWidth, true);
  const y = coefficients(height, resizedHeight, false);
  for (let dy = 0; dy < resizedHeight; dy++) {
    const sy = y.offsets[dy];
    const row0 = Math.max(0, Math.min(height - 1, sy)) * width * 3;
    const row1 = Math.max(0, Math.min(height - 1, sy + 1)) * width * 3;
    const b0 = y.weights[dy * 2];
    const b1 = y.weights[dy * 2 + 1];
    for (let dx = 0; dx < resizedWidth; dx++) {
      const sx = x.offsets[dx];
      const left = sx * 3;
      const right = Math.min(width - 1, sx + 1) * 3;
      const a0 = x.weights[dx * 2];
      const a1 = x.weights[dx * 2 + 1];
      const output = ((dy + padTop) * 512 + dx + padLeft) * 3;
      for (let channel = 0; channel < 3; channel++) {
        let value;
        if (half) {
          const top = (dy * 2 * width + dx * 2) * 3 + channel;
          value = (rgb[top] + rgb[top + 3] + rgb[top + width * 3] + rgb[top + width * 3 + 3] + 2) >> 2;
        } else {
          const h0 = rgb[row0 + left + channel] * a0 + rgb[row0 + right + channel] * a1;
          const h1 = rgb[row1 + left + channel] * a0 + rgb[row1 + right + channel] * a1;
          value = (((b0 * (h0 >> 4)) >> 16) + ((b1 * (h1 >> 4)) >> 16) + 2) >> 2;
        }
        letterbox[output + channel] = value;
      }
    }
  }
  const plane = 512 * 512;
  const tensor = new Float32Array(plane * 3);
  for (let pixel = 0; pixel < plane; pixel++) {
    for (let channel = 0; channel < 3; channel++) tensor[channel * plane + pixel] = letterbox[pixel * 3 + channel] / 255;
  }
  return { letterbox, tensor, geometry: { resizedWidth, resizedHeight, padLeft, padTop } };
}
