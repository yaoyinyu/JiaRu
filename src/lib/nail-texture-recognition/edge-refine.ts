/** 产品覆盖率alpha；原始radius、二值mask与模型对拍输出保持独立。 */
export function radialCoverageAlpha(
  radius: Float32Array, centerX: number, centerY: number,
  hard: Uint8Array, width: number, height: number, samples: 2 | 4 = 4
): Uint8ClampedArray {
  if (![2, 4].includes(samples) || !Number.isInteger(width) || !Number.isInteger(height) ||
      width < 1 || height < 1 || hard.length !== width * height || radius.length < 16 ||
      !Number.isFinite(centerX) || !Number.isFinite(centerY) ||
      radius.some(value => !Number.isFinite(value))) throw new Error("invalid_radial_coverage_input");
  const alpha = new Uint8ClampedArray(hard.length);
  const angularScale = radius.length / (2 * Math.PI);
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      const index = y * width + x;
      const value = hard[index] !== 0;
      let boundary = false;
      for (let oy = -1; oy <= 1 && !boundary; oy++) {
        for (let ox = -1; ox <= 1; ox++) {
          const xx = x + ox, yy = y + oy;
          const neighbor = xx >= 0 && yy >= 0 && xx < width && yy < height && hard[yy * width + xx] !== 0;
          if (neighbor !== value) { boundary = true; break; }
        }
      }
      if (!boundary) { alpha[index] = value ? 255 : 0; continue; }
      let covered = 0;
      for (let sy = 0; sy < samples; sy++) {
        for (let sx = 0; sx < samples; sx++) {
          const dx = x + (sx + .5) / samples - .5 - centerX;
          const dy = y + (sy + .5) / samples - .5 - centerY;
          const angle = Math.atan2(dy, dx);
          const wrapped = angle < 0 ? angle + 2 * Math.PI : angle;
          const bin = Math.min(radius.length - 1, Math.floor(wrapped * angularScale));
          if (radius[bin] >= Math.hypot(dx, dy)) covered++;
        }
      }
      alpha[index] = Math.floor(covered * 255 / (samples * samples) + .5);
    }
  }
  return alpha;
}
