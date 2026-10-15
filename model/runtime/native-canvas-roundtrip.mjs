// 原尺寸候选的整数逆映射；此模块不执行模型、缩放或概率插值。
export function originalMask(logits, presence, sourceSize, cropBox, nativeSize) {
  const [width, height] = sourceSize;
  const [x0, y0, x1, y1] = cropBox;
  const [h, w] = nativeSize;
  if (![width, height, x0, y0, x1, y1, h, w].every(Number.isSafeInteger) ||
      width <= 0 || height <= 0 || h <= 0 || w <= 0 ||
      x0 < 0 || y0 < 0 || x1 > width || y1 > height || x1 - x0 !== w || y1 - y0 !== h ||
      !(logits instanceof Float32Array) || logits.length !== h * w || !Number.isFinite(presence)) {
    throw new Error('reconstruction_mismatch: native integer geometry or head shape');
  }
  if (!logits.every(Number.isFinite)) throw new Error('nonfinite native mask');
  const output = new Uint8Array(width * height);
  if (presence >= 0) {
    for (let y = 0; y < h; y++) {
      for (let x = 0; x < w; x++) output[(y + y0) * width + x + x0] = Number(logits[y * w + x] >= 0);
    }
  }
  return output;
}

export function packedMask(pixels) {
  if (!(pixels instanceof Uint8Array) || !pixels.every(v => v === 0 || v === 1)) throw new Error('binary pixels required');
  const packed = new Uint8Array(Math.ceil(pixels.length / 8));
  for (let i = 0; i < pixels.length; i++) packed[i >> 3] |= pixels[i] << (i & 7);
  return packed;
}

export function canvasReadback(pixels, sourceSize) {
  const [width, height] = sourceSize;
  if (pixels.length !== width * height) throw new Error('full source canvas required');
  const canvas = new OffscreenCanvas(width, height);
  const context = canvas.getContext('2d', { willReadFrequently: true });
  if (!context) throw new Error('actual 2D context unavailable');
  const image = context.createImageData(width, height);
  for (let i = 0; i < pixels.length; i++) {
    image.data[i * 4] = image.data[i * 4 + 1] = image.data[i * 4 + 2] = pixels[i] * 255;
    image.data[i * 4 + 3] = 255;
  }
  context.putImageData(image, 0, 0);
  const actual = context.getImageData(0, 0, width, height).data;
  const result = new Uint8Array(pixels.length);
  for (let i = 0; i < result.length; i++) {
    const red = actual[i * 4];
    if ((red !== 0 && red !== 255) || actual[i * 4 + 1] !== red ||
        actual[i * 4 + 2] !== red || actual[i * 4 + 3] !== 255) throw new Error('canvas storage changed');
    result[i] = red / 255;
    if (result[i] !== pixels[i]) throw new Error('canvas readback pixel difference');
  }
  canvas.width = canvas.height = 1;
  return result;
}
