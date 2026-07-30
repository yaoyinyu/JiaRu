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
  /** 甲面横轴在画面中的方向；与 angle 不垂直时表示透视剪切。 */
  transverseAngle?: number;
}

export interface NailGeometryOptions {
  /** MediaPipe z=1 对应的显示像素数；object-cover 裁切时应传入缩放后源视频宽度。 */
  zScale?: number;
}

export interface NailAffineTransform {
  a: number;
  b: number;
  c: number;
  d: number;
  e: number;
  f: number;
}

export const NAIL_TIPS = [4, 8, 12, 16, 20] as const;
export const NAIL_DIPS = [3, 7, 11, 15, 19] as const;
export const NAIL_PIPS = [2, 6, 10, 14, 18] as const;
// MediaPipe TIP→DIP 是远端指骨长度。以下比例按真实甲面通常覆盖远端指骨
// 约 2/3 的视觉关系校正，避免旧参数在高清摄像头下呈现为指尖小圆点。
export const NAIL_OFFSET_RATIOS = [0.3, 0.34, 0.34, 0.33, 0.31] as const;
export const NAIL_LENGTH_RATIOS = [0.68, 0.72, 0.74, 0.7, 0.64] as const;
export const NAIL_WIDTH_RATIOS = [0.62, 0.56, 0.54, 0.52, 0.45] as const;
// 远端指骨 / 中段指骨的近似解剖比例，用中段指骨稳定远端深度尺度。
const DISTAL_TO_MIDDLE_RATIOS = [0.86, 0.76, 0.74, 0.73, 0.72] as const;

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
  height: number,
  options: NailGeometryOptions = {},
): NailGeometry | null {
  if (finger < 0 || finger > 4) return null;
  const tip = landmarks[NAIL_TIPS[finger]];
  const dip = landmarks[NAIL_DIPS[finger]];
  const pip = landmarks[NAIL_PIPS[finger]];
  if (!tip || !dip) return null;

  const tx = tip.x * width;
  const ty = tip.y * height;
  const zScale = options.zScale ?? width;
  let vx = (tip.x - dip.x) * width;
  let vy = (tip.y - dip.y) * height;
  let distalLength = Math.hypot(vx, vy);

  if (distalLength < 4 && pip) {
    vx = (dip.x - pip.x) * width;
    vy = (dip.y - pip.y) * height;
    distalLength = Math.hypot(vx, vy);
  }
  if (distalLength < 4) return null;

  // 轻量融合中段方向，减少 TIP 单点抖动；弯折过大时仍以远端方向为准。
  let ux = vx / distalLength;
  let uy = vy / distalLength;
  if (pip) {
    const middleX = (dip.x - pip.x) * width;
    const middleY = (dip.y - pip.y) * height;
    const middle2d = Math.hypot(middleX, middleY);
    if (middle2d >= 4) {
      const middleUx = middleX / middle2d;
      const middleUy = middleY / middle2d;
      if (ux * middleUx + uy * middleUy > 0.6) {
        const blendedX = ux * 0.82 + middleUx * 0.18;
        const blendedY = uy * 0.82 + middleUy * 0.18;
        const blendedLength = Math.hypot(blendedX, blendedY);
        ux = blendedX / blendedLength;
        uy = blendedY / blendedLength;
      }
    }
  }

  const distalDepth = ((tip.z ?? 0) - (dip.z ?? 0)) * zScale;
  const distal3d = Math.hypot(vx, vy, distalDepth);
  let stableDistal3d = distal3d;
  if (pip) {
    const middleX = (dip.x - pip.x) * width;
    const middleY = (dip.y - pip.y) * height;
    const middleDepth = ((dip.z ?? 0) - (pip.z ?? 0)) * zScale;
    const middle3d = Math.hypot(middleX, middleY, middleDepth);
    if (middle3d >= 4) {
      const anatomicalEstimate = middle3d * DISTAL_TO_MIDDLE_RATIOS[finger];
      // 远端定位保留主要权重，中段只抑制单帧深度噪声与透视缩短。
      stableDistal3d = distal3d * 0.68 + anatomicalEstimate * 0.32;
    }
  }

  const longitudinalProjection = clamp(distalLength / Math.max(distal3d, 0.001), 0.24, 1);
  const nailLength = stableDistal3d * NAIL_LENGTH_RATIOS[finger] * longitudinalProjection;

  // 用手背平面法向与远端指骨轴构造甲面横轴。这样手指侧转时甲面会自然
  // 变窄并产生剪切，而不是始终绘制一个正对镜头的旋转椭圆。
  let transverseAngle = normalizeAngle(Math.atan2(uy, ux) + Math.PI / 2);
  let transverseProjection = 1;
  const wrist = landmarks[0];
  const indexMcp = landmarks[5];
  const middleMcp = landmarks[9];
  const pinkyMcp = landmarks[17];
  if (wrist && indexMcp && middleMcp && pinkyMcp) {
    const across = {
      x: (indexMcp.x - pinkyMcp.x) * width,
      y: (indexMcp.y - pinkyMcp.y) * height,
      z: ((indexMcp.z ?? 0) - (pinkyMcp.z ?? 0)) * zScale,
    };
    const along = {
      x: (middleMcp.x - wrist.x) * width,
      y: (middleMcp.y - wrist.y) * height,
      z: ((middleMcp.z ?? 0) - (wrist.z ?? 0)) * zScale,
    };
    const normal = {
      x: across.y * along.z - across.z * along.y,
      y: across.z * along.x - across.x * along.z,
      z: across.x * along.y - across.y * along.x,
    };
    const normalLength = Math.hypot(normal.x, normal.y, normal.z);
    if (normalLength > 0.001 && distal3d > 0.001) {
      const nx = normal.x / normalLength;
      const ny = normal.y / normalLength;
      const nz = normal.z / normalLength;
      const ax = vx / distal3d;
      const ay = vy / distal3d;
      const az = distalDepth / distal3d;
      let crossX = ny * az - nz * ay;
      let crossY = nz * ax - nx * az;
      const crossZ = nx * ay - ny * ax;
      const crossLength = Math.hypot(crossX, crossY, crossZ);
      if (crossLength > 0.001) {
        crossX /= crossLength;
        crossY /= crossLength;
        transverseProjection = clamp(Math.hypot(crossX, crossY), 0.3, 1);
        const defaultCrossX = Math.cos(transverseAngle);
        const defaultCrossY = Math.sin(transverseAngle);
        if (crossX * defaultCrossX + crossY * defaultCrossY < 0) {
          crossX *= -1;
          crossY *= -1;
        }
        transverseAngle = normalizeAngle(Math.atan2(crossY, crossX));
      }
    }
  }

  const centerOffset = nailLength * (
    NAIL_OFFSET_RATIOS[finger] / NAIL_LENGTH_RATIOS[finger]
  );

  return {
    cx: tx - ux * centerOffset,
    cy: ty - uy * centerOffset,
    length: nailLength,
    width: stableDistal3d * NAIL_WIDTH_RATIOS[finger] * transverseProjection,
    angle: normalizeAngle(Math.atan2(uy, ux) + Math.PI / 2),
    transverseAngle,
  };
}

export function mapGeometryScale(geometry: NailGeometry, scale: number): NailGeometry {
  return {
    cx: geometry.cx * scale,
    cy: geometry.cy * scale,
    length: geometry.length * scale,
    width: geometry.width * scale,
    angle: geometry.angle,
    ...(geometry.transverseAngle == null
      ? {}
      : { transverseAngle: geometry.transverseAngle }),
  };
}

/** Canvas 2D 仿射矩阵：局部 -Y 为指尖方向，局部 +X 为甲面横轴。 */
export function createNailAffineTransform(
  geometry: NailGeometry,
): NailAffineTransform {
  const transverseAngle = geometry.transverseAngle ?? geometry.angle;
  return {
    a: Math.cos(transverseAngle),
    b: Math.sin(transverseAngle),
    c: -Math.sin(geometry.angle),
    d: Math.cos(geometry.angle),
    e: geometry.cx,
    f: geometry.cy,
  };
}

/** 应用用户级贴合微调；正 offset 沿甲面长轴向指根移动。 */
export function adjustNailGeometry(
  geometry: NailGeometry,
  scale: number,
  rootOffset: number,
  widthScale: number = scale,
): NailGeometry {
  const safeScale = clamp(scale, 0.75, 1.4);
  const safeWidthScale = clamp(widthScale, 0.7, 1.45);
  const safeOffset = clamp(rootOffset, -0.2, 0.2);
  const rootDirectionX = -Math.sin(geometry.angle);
  const rootDirectionY = Math.cos(geometry.angle);
  return {
    cx: geometry.cx + rootDirectionX * geometry.length * safeOffset,
    cy: geometry.cy + rootDirectionY * geometry.length * safeOffset,
    length: geometry.length * safeScale,
    width: geometry.width * safeWidthScale,
    angle: geometry.angle,
    ...(geometry.transverseAngle == null
      ? {}
      : { transverseAngle: geometry.transverseAngle }),
  };
}
