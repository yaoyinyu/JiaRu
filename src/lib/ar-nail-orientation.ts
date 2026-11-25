import { NAIL_DIPS, NAIL_PIPS, NAIL_TIPS, type NailLandmark } from "./nail-geometry.ts";

/** 手指 MCP 索引（拇→小）。 */
export const NAIL_MCPS = [1, 5, 9, 13, 17] as const;

/** 甲板法向朝镜头分量的判定带：|nz| 小于此值视为侧缘（edge-on）。 */
export const NAIL_FACING_COS = 0.25;
/** 累计屈曲角超过此值进入蜷曲几何分支。 */
export const CURL_GEOMETRY_THRESHOLD = 0.6;

export interface Vec3 {
  x: number;
  y: number;
  z: number;
}

export interface FingerNailOrientation {
  /** 累计屈曲角 Θ = PIP 屈曲 + DIP 屈曲（弧度）。 */
  curl: number;
  /** 甲板法向（单位向量，z 负 = 朝镜头）。 */
  nailNormal: Vec3;
  /** 甲板明确朝镜头。 */
  facingCamera: boolean;
  /** 甲板侧缘对镜头（|nz| 小），需佐证信号裁决。 */
  edgeOn: boolean;
  /** 远端指骨 2D 单位方向。 */
  distal2D: { x: number; y: number };
  distal2DLength: number;
  distal3DLength: number;
}

export interface FingerJointPoints {
  tip: NailLandmark;
  dip: NailLandmark;
  pip: NailLandmark;
  mcp?: NailLandmark;
}

function diff3(a: NailLandmark, b: NailLandmark, zScale: number): Vec3 {
  return {
    x: a.x - b.x,
    y: a.y - b.y,
    z: ((a.z ?? 0) - (b.z ?? 0)) * zScale,
  };
}

function dot(a: Vec3, b: Vec3): number {
  return a.x * b.x + a.y * b.y + a.z * b.z;
}

function cross(a: Vec3, b: Vec3): Vec3 {
  return {
    x: a.y * b.z - a.z * b.y,
    y: a.z * b.x - a.x * b.z,
    z: a.x * b.y - a.y * b.x,
  };
}

function length(v: Vec3): number {
  return Math.hypot(v.x, v.y, v.z);
}

function normalize(v: Vec3): Vec3 | null {
  const len = length(v);
  if (len < 1e-6) return null;
  return { x: v.x / len, y: v.y / len, z: v.z / len };
}

function angleBetween(a: Vec3, b: Vec3): number {
  const la = length(a);
  const lb = length(b);
  if (la < 1e-6 || lb < 1e-6) return 0;
  const c = Math.max(-1, Math.min(1, dot(a, b) / (la * lb)));
  return Math.acos(c);
}

/** Rodrigues 旋转：v 绕单位轴 k 转 θ。 */
function rotate(v: Vec3, k: Vec3, theta: number): Vec3 {
  const c = Math.cos(theta);
  const s = Math.sin(theta);
  const kv = cross(k, v);
  const kd = dot(k, v) * (1 - c);
  return {
    x: v.x * c + kv.x * s + k.x * kd,
    y: v.y * c + kv.y * s + k.y * kd,
    z: v.z * c + kv.z * s + k.z * kd,
  };
}

/**
 * 手背平面法向，定向到「手背侧」。
 *
 * 几何法向取三 MCP 三角（腕出画时由食指/小指 MCP 中点构面，与 nail-geometry 同口径）；
 * 符号由全局朝向决定：dorsum 朝镜头时手背法向 z<0，palm 朝镜头时手背法向 z>0，
 * ambiguous 用掌-指根深度差符号兜底。
 */
export function computeHandDorsumNormal(
  lm: readonly NailLandmark[],
  orientation: "dorsum" | "palm" | "ambiguous",
  palmDepthDiff: number,
  zScale: number,
): Vec3 | null {
  const wrist = lm[0];
  const indexMcp = lm[5];
  const middleMcp = lm[9];
  const pinkyMcp = lm[17];
  if (!indexMcp || !middleMcp || !pinkyMcp) return null;

  const across = diff3(indexMcp, pinkyMcp, zScale);
  const wristInFrame = wrist != null
    && wrist.x >= 0.05 && wrist.x <= 0.95
    && wrist.y >= 0.05 && wrist.y <= 0.95;
  const base: NailLandmark = wristInFrame && wrist ? wrist : {
    x: (indexMcp.x + pinkyMcp.x) / 2,
    y: (indexMcp.y + pinkyMcp.y) / 2,
    z: ((indexMcp.z ?? 0) + (pinkyMcp.z ?? 0)) / 2,
  };
  const along = diff3(middleMcp, base, zScale);
  let n = normalize(cross(across, along));
  if (!n) return null;

  const target = orientation === "palm" ? 1 : orientation === "dorsum" ? -1 : (palmDepthDiff > 0 ? 1 : -1);
  if (n.z !== 0 && (n.z > 0 ? 1 : -1) !== target) {
    n = { x: -n.x, y: -n.y, z: -n.z };
  }
  return n;
}

/**
 * 逐指甲板朝向先验。
 *
 * 甲板法向 = 手背法向绕手指横轴（中段→远端叉积）旋转累计屈曲角 Θ。
 * 伸直 Θ≈0 时甲板法向≈手背法向；握拳/钩指/掌面回蜷时 Θ 增大，
 * 甲板法向随之转向镜头，从而识别「蜷曲但甲面朝镜头」的展示姿势。
 */
export function computeFingerNailOrientation(
  points: FingerJointPoints,
  dorsumNormal: Vec3,
  zScale: number,
): FingerNailOrientation | null {
  const d3 = diff3(points.tip, points.dip, zScale);
  const m3 = diff3(points.dip, points.pip, zScale);
  const dLen = length(d3);
  const mLen = length(m3);
  if (dLen < 1e-6 || mLen < 1e-6) return null;

  const dipFlex = angleBetween(m3, d3);
  const p3 = points.mcp ? diff3(points.pip, points.mcp, zScale) : null;
  const pipFlex = p3 ? angleBetween(p3, m3) : 0;
  const curl = dipFlex + pipFlex;

  let nailNormal = dorsumNormal;
  if (curl >= 1e-3) {
    const hinge = normalize(cross(m3, d3));
    if (hinge) nailNormal = rotate(dorsumNormal, hinge, curl);
  }

  const distal2DLength = Math.hypot(d3.x, d3.y);
  const distal2D = distal2DLength > 1e-6
    ? { x: d3.x / distal2DLength, y: d3.y / distal2DLength }
    : { x: 0, y: -1 };

  return {
    curl,
    nailNormal,
    facingCamera: nailNormal.z < -NAIL_FACING_COS,
    edgeOn: Math.abs(nailNormal.z) <= NAIL_FACING_COS,
    distal2D,
    distal2DLength,
    distal3DLength: dLen,
  };
}

/** 供 ArView 以平滑关键点构造逐指关节点。 */
export function fingerJointPoints(
  lm: readonly NailLandmark[],
  finger: number,
  smoothed: { tip: NailLandmark; dip: NailLandmark; pip: NailLandmark },
): FingerJointPoints {
  return {
    tip: smoothed.tip,
    dip: smoothed.dip,
    pip: smoothed.pip,
    mcp: lm[NAIL_MCPS[finger]],
  };
}

export { NAIL_TIPS, NAIL_DIPS, NAIL_PIPS };