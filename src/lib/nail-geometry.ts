export interface NailLandmark {
  x: number;
  y: number;
  z?: number;
}

export interface NailGeometry {
  cx: number;
  cy: number;
  length: number;
  width: number;
  angle: number;
}

export const NAIL_TIPS = [4, 8, 12, 16, 20] as const;
export const NAIL_DIPS = [3, 7, 11, 15, 19] as const;
export const NAIL_PIPS = [2, 6, 10, 14, 18] as const;
export const NAIL_OFFSET_RATIOS = [0.22, 0.28, 0.28, 0.26, 0.24] as const;
export const NAIL_LENGTH_RATIOS = [0.5, 0.55, 0.58, 0.54, 0.48] as const;
export const NAIL_WIDTH_RATIOS = [0.52, 0.48, 0.46, 0.44, 0.36] as const;

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

export function normalizeAngle(angle: number): number {
  let result = angle;
  while (result > Math.PI) result -= Math.PI * 2;
  while (result <= -Math.PI) result += Math.PI * 2;
  return result;
}

export function smoothAngle(previous: number, current: number, alpha: number): number {
  return normalizeAngle(previous + normalizeAngle(current - previous) * alpha);
}

/** 计算目标像素坐标系中的指甲几何。指甲路径的局部 -Y 方向指向指尖。 */
export function computeNailGeometry(
  landmarks: readonly NailLandmark[],
  finger: number,
  width: number,
  height: number
): NailGeometry | null {
  if (finger < 0 || finger > 4) return null;
  const tip = landmarks[NAIL_TIPS[finger]];
  const dip = landmarks[NAIL_DIPS[finger]];
  const pip = landmarks[NAIL_PIPS[finger]];
  if (!tip || !dip) return null;

  const tx = tip.x * width;
  const ty = tip.y * height;
  let vx = (tip.x - dip.x) * width;
  let vy = (tip.y - dip.y) * height;
  let distalLength = Math.hypot(vx, vy);

  if (distalLength < 4 && pip) {
    vx = (dip.x - pip.x) * width;
    vy = (dip.y - pip.y) * height;
    distalLength = Math.hypot(vx, vy);
  }
  if (distalLength < 4) return null;

  const ux = vx / distalLength;
  const uy = vy / distalLength;
  const zDelta = Math.abs((tip.z ?? 0) - (dip.z ?? 0));
  const perspective = clamp(1 - zDelta * 3, 0.78, 1);

  return {
    cx: tx - ux * distalLength * NAIL_OFFSET_RATIOS[finger],
    cy: ty - uy * distalLength * NAIL_OFFSET_RATIOS[finger],
    length: distalLength * NAIL_LENGTH_RATIOS[finger] * perspective,
    width: distalLength * NAIL_WIDTH_RATIOS[finger] * Math.sqrt(perspective),
    angle: normalizeAngle(Math.atan2(vy, vx) + Math.PI / 2),
  };
}

export function mapGeometryScale(geometry: NailGeometry, scale: number): NailGeometry {
  return {
    cx: geometry.cx * scale,
    cy: geometry.cy * scale,
    length: geometry.length * scale,
    width: geometry.width * scale,
    angle: geometry.angle,
  };
}
