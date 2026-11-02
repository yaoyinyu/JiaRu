/**
 * AR 三步流程的步骤条派生与复核应用提示文案（frontend-interaction-redesign-plan §7.1/§7.2）。
 *
 * 边界：
 * - 纯派生逻辑：输入页面当前的布尔状态，输出顶部步骤条数据；不触碰识别、媒体流或位图；
 * - 步骤语义：选择来源（Step 1）→ 提取与复核（Step 2）→ 试戴与校准（Step 3）；
 * - 只展示进度与提示，不新增「自动识别成功」类宣称。
 */

import { AR_STEPS, type ArStepId } from "./ar-review-flow.ts";

export type ArStepStatus = "done" | "active" | "todo";

export interface ArStepProgressInput {
  /** 任一手指已有纹理（来源已产出结果） */
  hasAnyTexture: boolean;
  /** 提取与复核进行中：裁剪弹层 / 选择器弹层 / 覆盖前复核界面任一打开 */
  extractionActive: boolean;
  /** 摄像头会话运行中（ArView 已就绪） */
  cameraActive: boolean;
}

export interface ArStepProgress {
  current: ArStepId;
  steps: { id: ArStepId; label: string; status: ArStepStatus }[];
}

/**
 * 由页面状态派生三步进度：
 * - 弹层 / 复核界面打开时处于 Step 2（提取与复核）；
 * - 否则摄像头运行或已有纹理时处于 Step 3（试戴与校准）；
 * - 其余情况停留在 Step 1（选择来源）。
 */
export function resolveArStepProgress(input: ArStepProgressInput): ArStepProgress {
  const current: ArStepId = input.extractionActive
    ? "extract"
    : input.cameraActive || input.hasAnyTexture
      ? "tryon"
      : "source";

  const sourceStatus: ArStepStatus = current === "source" ? "active" : "done";
  const extractStatus: ArStepStatus =
    current === "extract" ? "active" : input.hasAnyTexture ? "done" : "todo";
  const tryonStatus: ArStepStatus = current === "tryon" ? "active" : "todo";

  return {
    current,
    steps: [
      { id: "source", label: AR_STEPS[0].label, status: sourceStatus },
      { id: "extract", label: AR_STEPS[1].label, status: extractStatus },
      { id: "tryon", label: AR_STEPS[2].label, status: tryonStatus },
    ],
  };
}

/** 复核界面「应用到试戴」成功后的提示（§7.2：应用后提供撤销提示）。 */
export function formatArReviewAppliedNotice(input: {
  appliedCount: number;
  reviewCount: number;
}): string {
  const suffix = input.reviewCount > 0 ? `，其中 ${input.reviewCount} 指建议复核` : "";
  return `已应用 ${input.appliedCount} 指纹理${suffix}，可撤销本次替换。`;
}
