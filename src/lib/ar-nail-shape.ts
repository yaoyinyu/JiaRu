/**
 * AR 渲染用甲型模板与风格映射。
 *
 * 职责边界：这里只做「甲型类别 → 渲染形状参数 / 光泽系数」的纯映射，
 * 以及纹理模式渲染长度的长宽比保真计算（computeTextureRenderPlan）；
 * 不做识别与分析（分析在 nail-texture-recognition/texture-analysis.ts）。
 * round 档的字段值必须与历史硬编码常量逐字段一致，保证未传入 nailStyles 时渲染不变。
 */

export type NailShapeClass = "round" | "square" | "almond" | "stiletto";

export interface NailRenderStyle {
  shape?: NailShapeClass | null;
  /** 0..1，来自纹理分析的光泽度；缺省表示不调整 */
  gloss?: number | null;
}

/** drawNailShape 的形状参数，均为相对比率（与历史硬编码同口径） */
export interface NailShapeProfile {
  /** 尖端开口收窄量 × nw：越大尖端越窄，0.46 时近似收成一点 */
  tipNarrow: number;
  /** 尖端上拱控制点 × hl：方甲接近 0，圆甲较大 */
  tipArch: number;
  /** 侧线贝塞尔控制点长度 × hl：越小侧线越直 */
  sideCurve: number;
  /** 侧线外扩系数 × cpLen：杏仁/尖甲沿侧线锥化更明显 */
  sideFlare: number;
  /** 根部凸起 × hl */
  rootBulge: number;
}

// 历史 round 甲型常量（原 ArView.tsx 内硬编码，迁来这里作为唯一来源）
export const ROUND_TIP_NARROW = [0.12, 0.08, 0.07, 0.08, 0.06] as const;
export const ROUND_SIDE_CURVE = [0.5, 0.55, 0.55, 0.52, 0.45] as const;
export const ROUND_ROOT_BULGE = [0.06, 0.08, 0.08, 0.07, 0.05] as const;
const ROUND_TIP_ARCH = 0.15;
const ROUND_SIDE_FLARE = 0.3;

const NON_ROUND_PROFILES: Record<
  Exclude<NailShapeClass, "round">,
  Omit<NailShapeProfile, "rootBulge">
> = {
  square: { tipNarrow: 0.02, tipArch: 0.04, sideCurve: 0.32, sideFlare: 0.18 },
  almond: { tipNarrow: 0.16, tipArch: 0.12, sideCurve: 0.62, sideFlare: 0.42 },
  stiletto: { tipNarrow: 0.46, tipArch: 0.03, sideCurve: 0.78, sideFlare: 0.55 },
};

export function getNailShapeProfile(
  shape: NailShapeClass | null | undefined,
  fingerIdx: number,
): NailShapeProfile {
  const rootBulge = ROUND_ROOT_BULGE[fingerIdx] ?? ROUND_ROOT_BULGE[2];
  if (!shape || shape === "round") {
    return {
      tipNarrow: ROUND_TIP_NARROW[fingerIdx] ?? ROUND_TIP_NARROW[2],
      tipArch: ROUND_TIP_ARCH,
      sideCurve: ROUND_SIDE_CURVE[fingerIdx] ?? ROUND_SIDE_CURVE[2],
      sideFlare: ROUND_SIDE_FLARE,
      rootBulge,
    };
  }
  return { ...NON_ROUND_PROFILES[shape], rootBulge };
}

/**
 * 纹理模式的渲染长度计划：长宽比保真（「原封不动」贴回）。
 *
 * 纹理位图在提取时已归一化（甲尖朝上、紧致裁剪、甲面充满位图），
 * 其 height/width 就是设计甲面的真实长宽比。渲染时：
 *   - 宽度对齐用户真实甲面（geometry.width，含宽度滑杆）；
 *   - 渲染长度 = 宽度 × 纹理长宽比，等比缩放、比例不压扁；
 *   - 甲根边缘锚定在估算甲面的甲根边缘，延长部分向甲尖自然伸出；
 *   - 不短于估算甲面长度（保证盖满真实甲面），上限 maxLengthScale × 估算长度（防极端长宽比）。
 * textureAspect 非法（非有限/≤0）时退回估算长度（不延长）。
 */
export interface TextureRenderPlan {
  cx: number;
  cy: number;
  length: number;
}

export function computeTextureRenderPlan(
  geometry: { cx: number; cy: number; length: number; width: number; angle: number },
  textureAspect: number,
  maxLengthScale: number = 3,
): TextureRenderPlan {
  const safeAspect =
    Number.isFinite(textureAspect) && textureAspect > 0 ? textureAspect : 1;
  const cap = Math.max(geometry.length, geometry.length * maxLengthScale);
  const length = Math.max(geometry.length, Math.min(geometry.width * safeAspect, cap));
  const delta = (length - geometry.length) / 2;
  // 甲尖方向 = 局部 −Y 轴的世界方向 = (sin(angle), −cos(angle))，与
  // createNailAffineTransform/adjustNailGeometry 的甲根方向约定互为反向。
  return {
    cx: geometry.cx + Math.sin(geometry.angle) * delta,
    cy: geometry.cy - Math.cos(geometry.angle) * delta,
    length,
  };
}

/** 光泽度 0..1 → 渲染高光/菲涅尔系数乘子；未提供时为 1（维持现状） */
export function glossToRenderFactor(gloss: number | null | undefined): number {
  if (gloss == null || !Number.isFinite(gloss)) return 1;
  const clamped = Math.max(0, Math.min(1, gloss));
  return Math.max(0.55, Math.min(1.35, 0.55 + clamped * 0.8));
}
