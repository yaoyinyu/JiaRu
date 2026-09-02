/**
 * Seedream（火山方舟）生图专用精简提示词。
 *
 * 背景与依据：火山方舟文档建议中文提示词不超过 300 字，字数过多会导致
 * 信息分散、模型忽略细节。原 Agnes 链路的隐藏系统提示词实测约 1471 字
 * （组装后最大 2143 字），为文档建议的 7 倍，不适用于 Seedream。
 *
 * 本模块为 Seedream 单独设计精简约束（系统词 ≤120 字），只保留对手部
 * 出图质量最关键的核心约束：手数量、五指、无畸形、无穿模；图生图额外
 * 强调"只改指甲、其余原样保留"。与 ai-hand-anatomy-prompt.ts 完全独立，
 * 修改本模块不得影响 Agnes 链路。
 */

import { AI_IMAGE_SCENE_SUFFIX } from "./ai-hand-anatomy-prompt.ts";

/** Seedream 文生图系统提示词（用户不可见，前置注入）。 */
export const SEEDREAM_T2I_SYSTEM_PROMPT =
  "画面只出现一只手（双手动作最多两只手），严禁第三只手；" +
  "每只手恰好五根手指，不得多指、缺指、粘连或畸形；" +
  "手势自然、比例正确、无穿模。以下内容为美甲设计描述：";

/** Seedream 图生图系统提示词（用户不可见，前置注入）。 */
export const SEEDREAM_I2I_SYSTEM_PROMPT =
  "以上传参考图为唯一基准：保持手部数量、五指结构、姿势、肤色、服装与背景完全不变，" +
  "仅在参考图中可见的指甲上绘制所描述的美甲设计；" +
  "禁止改动指甲以外的任何内容，禁止增删指甲或改变手势。以下内容为美甲设计描述：";

/**
 * 组装 Seedream 文生图完整提示词：
 * 精简系统约束 → 用户提示词 → 美甲场景后缀。
 */
export function assembleSeedreamPrompt(userPrompt: string): string {
  return `${SEEDREAM_T2I_SYSTEM_PROMPT}${userPrompt}, ${AI_IMAGE_SCENE_SUFFIX}`;
}

/**
 * 组装 Seedream 图生图完整提示词：
 * 精简图生图约束 → 用户提示词 → 美甲场景后缀。
 */
export function assembleSeedreamEditPrompt(userPrompt: string): string {
  return `${SEEDREAM_I2I_SYSTEM_PROMPT}${userPrompt}, ${AI_IMAGE_SCENE_SUFFIX}`;
}
