import type { NailMask } from "./types.ts";

export function normalizeHalfTurnAngle(angle: number): number {
  let result = angle;
  while (result > Math.PI / 2) result -= Math.PI;
  while (result <= -Math.PI / 2) result += Math.PI;
  return result;
}

export function estimateMaskPrincipalAngle(mask: NailMask): number | null {
  let total = 0;
  let meanX = 0;
  let meanY = 0;

  for (let y = 0; y < mask.height; y++) {
    for (let x = 0; x < mask.width; x++) {
      if (!mask.data[y * mask.width + x]) continue;
      total++;
      meanX += x;
      meanY += y;
    }
  }

  if (total < 4) return null;
  meanX /= total;
  meanY /= total;

  let mu20 = 0;
  let mu02 = 0;
  let mu11 = 0;

  for (let y = 0; y < mask.height; y++) {
    for (let x = 0; x < mask.width; x++) {
      if (!mask.data[y * mask.width + x]) continue;
      const dx = x - meanX;
      const dy = y - meanY;
      mu20 += dx * dx;
      mu02 += dy * dy;
      mu11 += dx * dy;
    }
  }

  const trace = mu20 + mu02;
  const delta = Math.sqrt((mu20 - mu02) ** 2 + 4 * mu11 * mu11);
  const major = (trace + delta) / 2;
  const minor = (trace - delta) / 2;
  if (major <= 0) return null;
  const axisRatio = minor <= 1e-6 ? Number.POSITIVE_INFINITY : major / minor;
  if (axisRatio < 1.1) return null;

  const axisAngle = 0.5 * Math.atan2(2 * mu11, mu20 - mu02);
  return normalizeHalfTurnAngle(axisAngle + Math.PI / 2);
}

/** 归一化告警码：掩膜主轴与参考角的交叉检查不一致。 */
export const WARNING_ORIENTATION_DISAGREEMENT = "normalization_orientation_disagreement";
/** 归一化告警码：甲尖方向无法确定（无参考角且主轴为半转角）。 */
export const WARNING_TIP_DIRECTION_UNKNOWN = "normalization_tip_direction_unknown";
/** 主轴角与参考角交叉检查的分歧上限。 */
export const ORIENTATION_DISAGREEMENT_LIMIT_RADIANS = (25 * Math.PI) / 180;

export type MaskTextureRotationSource = "mask" | "mask+taper" | "mask+reference" | "reference" | "none";

/** 只在长尖端与宽甲床有明显非对称时推断方向；对称/平甲端保持待确认。 */
function inferTaperRotation(mask: NailMask, angle: number): number | null {
  const tx = Math.sin(angle), ty = -Math.cos(angle), xx = Math.cos(angle), xy = Math.sin(angle);
  let min = Infinity, max = -Infinity;
  for (let y = 0; y < mask.height; y++) for (let x = 0; x < mask.width; x++) {
    if (!mask.data[y * mask.width + x]) continue;
    const along = x * tx + y * ty; min = Math.min(min, along); max = Math.max(max, along);
  }
  const span = max - min;
  if (span < 8) return null;
  const left = new Float64Array(32).fill(Infinity), right = new Float64Array(32).fill(-Infinity);
  for (let y = 0; y < mask.height; y++) for (let x = 0; x < mask.width; x++) {
    if (!mask.data[y * mask.width + x]) continue;
    const bin = Math.min(31, Math.floor(((x * tx + y * ty - min) / span) * 32));
    const across = x * xx + y * xy; left[bin] = Math.min(left[bin], across); right[bin] = Math.max(right[bin], across);
  }
  const widths = Array.from(left, (v, i) => Number.isFinite(v) ? right[i] - v + 1 : 0);
  const widest = Math.max(...widths);
  if (span / widest < 1.35) return null;
  const mean = (a: number, b: number) => widths.slice(a, b).reduce((s, v) => s + v, 0) / (b - a);
  const low = mean(3, 11), high = mean(21, 29);
  if (low < high * .72 && high > widest * .82) return angle + Math.PI;
  if (high < low * .72 && low > widest * .82) return angle;
  return null;
}

export interface MaskTextureRotation {
  /**
   * 解析后的甲面横轴全角（弧度）。
   * 半转角仅描述轴向；甲尖方向由 referenceAngle 蕴含的指尖方向
   * （referenceAngle - π/2）消歧 180° 后补全为全角。
   * 把位图旋转 -rotation 即可让甲面横轴水平、甲尖朝上。
   */
  rotation: number;
  source: MaskTextureRotationSource;
  warnings: string[];
}

/**
 * 解析 mask 纹理的摆正旋转角。
 *
 * - 掩膜主轴角（半转角）优先：直接描述被提取内容的朝向；
 * - 有向 referenceAngle（手指关键点或人工确认）只用于两件事：
 *   ①为主轴角补全甲尖方向（消 180° 歧义）；②主轴不可用（近圆甲面）时兜底；
 * - 两者皆不可用时旋转 0，并给出甲尖方向未定告警；
 * - 主轴与参考角分歧超过 25° 时给出交叉检查告警（仍以主轴为准）。
 * - referenceIsDirected=false 时，仅明显收尖的轮廓可自动补全甲尖方向；其余提示复核。
 */
export function resolveMaskTextureRotation(
  mask: NailMask,
  referenceAngle?: number | null,
  referenceIsDirected: boolean = true,
): MaskTextureRotation {
  const principal = estimateMaskPrincipalAngle(mask);
  const reference =
    typeof referenceAngle === "number" && Number.isFinite(referenceAngle) ? referenceAngle : null;

  if (!referenceIsDirected && principal != null) {
    const tapered = inferTaperRotation(mask, principal);
    return tapered == null
      ? { rotation: principal, source: "mask", warnings: [WARNING_TIP_DIRECTION_UNKNOWN] }
      : { rotation: tapered, source: "mask+taper", warnings: [] };
  }

  if (principal == null) {
    if (reference == null || !referenceIsDirected) {
      return { rotation: 0, source: "none", warnings: [WARNING_TIP_DIRECTION_UNKNOWN] };
    }
    return { rotation: reference, source: "reference", warnings: [] };
  }
  if (reference == null) {
    return { rotation: principal, source: "mask", warnings: [WARNING_TIP_DIRECTION_UNKNOWN] };
  }

  const refTipX = Math.cos(reference - Math.PI / 2);
  const refTipY = Math.sin(reference - Math.PI / 2);
  const longX = Math.cos(principal - Math.PI / 2);
  const longY = Math.sin(principal - Math.PI / 2);
  const rotation = longX * refTipX + longY * refTipY >= 0 ? principal : principal + Math.PI;

  const warnings: string[] = [];
  if (
    Math.abs(normalizeHalfTurnAngle(principal - reference)) >
    ORIENTATION_DISAGREEMENT_LIMIT_RADIANS
  ) {
    warnings.push(WARNING_ORIENTATION_DISAGREEMENT);
  }
  return { rotation, source: "mask+reference", warnings };
}
