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

export type MaskTextureRotationSource = "mask" | "mask+reference" | "reference" | "none";

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
 * - referenceAngle（候选横轴角，如 region.angle）只用于两件事：
 *   ①为主轴角补全甲尖方向（消 180° 歧义）；②主轴不可用（近圆甲面）时兜底；
 * - 两者皆不可用时旋转 0，并给出甲尖方向未定告警；
 * - 主轴与参考角分歧超过 25° 时给出交叉检查告警（仍以主轴为准）。
 */
export function resolveMaskTextureRotation(
  mask: NailMask,
  referenceAngle?: number | null
): MaskTextureRotation {
  const principal = estimateMaskPrincipalAngle(mask);
  const reference =
    typeof referenceAngle === "number" && Number.isFinite(referenceAngle) ? referenceAngle : null;

  if (principal == null) {
    if (reference == null) {
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
