/**
 * AR 三步流程与低置信覆盖前复核的纯逻辑（frontend-interaction-redesign-plan §7.1/§7.2）。
 *
 * 边界：
 * - 本模块不做识别、不触碰媒体流；只对「是否有旧纹理 + 逐甲置信档位」
 *   做覆盖前决策，并产出复核界面文案与步骤条数据；
 * - 高置信路径保持一键应用；「继续调整/取消」不改变现有配置；
 * - 复核只是展示与确认门，不宣称识别能力提升。
 */

import type { NailTextureCandidateConfidence } from "./nail-texture-recognition/types.ts";

export type ArConfidence = NailTextureCandidateConfidence;

/** AR 顶部步骤条（§7.1）：选择来源 → 提取与复核 → 试戴与校准。 */
export type ArStepId = "source" | "extract" | "tryon";

export const AR_STEPS: readonly { id: ArStepId; label: string }[] = [
  { id: "source", label: "选择来源" },
  { id: "extract", label: "提取与复核" },
  { id: "tryon", label: "试戴与校准" },
];

/** 覆盖前决策动作（§7.2 规则表）。 */
export type ArReviewAction =
  /** 无旧纹理 + 高置信：自动应用。 */
  | "apply"
  /** 无旧纹理 + 中置信：自动应用，显示可复核提示。 */
  | "apply_with_notice"
  /** 无旧纹理 + 低置信：进入复核态。 */
  | "review"
  /** 有旧纹理 + 高置信：显示替换预览。 */
  | "replace_preview"
  /** 有旧纹理 + 中/低置信：必须确认。 */
  | "confirm";

/** 批次置信取整批最低档（任一甲低置信即按低置信处置）。 */
const CONFIDENCE_RANK: Record<ArConfidence, number> = {
  high: 2,
  medium: 1,
  low: 0,
};

/** 覆盖前决策（§7.2）：依有无旧纹理与整批最低置信档给出动作。 */
export function decideArReview(input: {
  hasExistingTexture: boolean;
  lowestConfidence: ArConfidence;
}): ArReviewAction {
  if (!input.hasExistingTexture) {
    if (input.lowestConfidence === "high") return "apply";
    if (input.lowestConfidence === "medium") return "apply_with_notice";
    return "review";
  }
  return input.lowestConfidence === "high" ? "replace_preview" : "confirm";
}

/** 逐甲置信汇总：识别数、建议复核数（低置信）与整批最低档。 */
export function summarizeArReview(confidences: readonly ArConfidence[]): {
  recognizedCount: number;
  reviewCount: number;
  reviewIndices: number[];
  lowest: ArConfidence | null;
} {
  const reviewIndices: number[] = [];
  let lowest: ArConfidence | null = null;
  confidences.forEach((confidence, index) => {
    if (confidence === "low") reviewIndices.push(index);
    if (!lowest || CONFIDENCE_RANK[confidence] < CONFIDENCE_RANK[lowest]) {
      lowest = confidence;
    }
  });
  return {
    recognizedCount: confidences.length,
    reviewCount: reviewIndices.length,
    reviewIndices,
    lowest,
  };
}

/** 复核界面摘要文案（§7.2）：「已识别 5 个甲面，其中 2 个建议复核」。 */
export function formatArReviewSummary(summary: {
  recognizedCount: number;
  reviewCount: number;
}): string {
  if (summary.recognizedCount === 0) return "未识别到甲面";
  if (summary.reviewCount === 0) return `已识别 ${summary.recognizedCount} 个甲面`;
  return `已识别 ${summary.recognizedCount} 个甲面，其中 ${summary.reviewCount} 个建议复核`;
}

/** 自动应用提示（中置信可复核口径，§7.2）。 */
export function formatArApplyNotice(input: {
  appliedCount: number;
  reviewCount: number;
}): string {
  const suffix = input.reviewCount > 0 ? `，其中 ${input.reviewCount} 指建议复核` : "";
  return `已自动提取并应用 ${input.appliedCount} 指纹理${suffix}，可重新打开选择器调整。`;
}
