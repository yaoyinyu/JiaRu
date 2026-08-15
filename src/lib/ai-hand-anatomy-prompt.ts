/**
 * AI 生图隐藏系统提示词（用户不可见）。
 *
 * 目的：底层生图模型对手部细节容易产生多指、缺指、手指粘连、手掌残缺、
 * 畸形、穿模、多只手等缺陷。发送请求时在用户提示词之前注入简短的手数量
 * 约束（前置），并在末尾附加完整解剖约束（后置），双保险约束模型输出
 * 解剖结构正确的手部，提升美甲场景的出图可用率。
 */

export const HAND_ANATOMY_SYSTEM_PROMPT =
  "描述中的动作决定手部数量：手持、手拿、手捏、手举、手指轻触等单手动作时，" +
  "画面中只出现一只手；手捧、手端、手托、双手合握、双手捧着等双手动作时，" +
  "画面中只出现两只手；绝对禁止第三只手。" +
  "每只手必须且只能有五根手指（一根拇指与四根手指），" +
  "不多不少，绝对禁止第六根手指、七根手指或任何数量错误的手指；" +
  "画面中只能出现一只手（单手近景场景）或最多两只手（双手场景），" +
  "绝对禁止出现第三只手、多余的手臂或任何额外的手部肢体；" +
  "手捧、手持、触摸道具（如茶杯、花束、糖果、手机等）时，" +
  "道具只能由画面中可见的这（两）只手接触，" +
  "严禁从画面外伸出额外的第三只手，也不得在画面内凭空出现多余的手；" +
  "每只手恰好五根完整、清晰、独立、自然弯曲的手指（一根拇指与四根手指），" +
  "手指数量精确为五根、形态分明、互不粘连、不分叉；" +
  "手掌完整无残缺、无多余组织；" +
  "双手场景中，两只手轮廓清晰、彼此分离，不得交叠、粘连、融合或互相穿插，" +
  "两只手的皮肤、手指与指甲必须边界分明，不得混成一体；" +
  "手指粗细长短比例自然协调，指关节位置正确；" +
  "手与指甲、饰品、道具之间不得相互穿模、穿插或重叠变形；" +
  "手部姿势自然放松，透视与光线正确。" +
  "再次强调：每只手恰好五根手指（一根拇指与四根手指），" +
  "绝不出现第六根手指、七根手指或缺失的手指；" +
  "整个画面严禁出现第三只手、多余的手部、多余的手臂或任何多余的肢体。" +
  "严禁出现任何手部缺陷：多指、六指、七指、缺指、手指不全、手指粘连、手指分叉、手掌残缺、畸形手、坏解剖、肢体变形、比例失调、肢体穿插穿模、双手交叠、双手粘连、双手融合、手指交叉缠绕、手指互相穿插、双手边界模糊、多余的手、多余的手臂、第三只手。" +
  "禁止：NO extra fingers, NO sixth finger, NO missing fingers, NO four fingers, NO fused fingers, NO webbed fingers, NO extra hands, NO third hand, NO more than two hands, NO multiple hands, NO additional hands, NO duplicate hands, NO merged hands, NO overlapping hands, NO tangled fingers, NO interlocked fingers, NO conjoined hands, NO blurred hand boundaries, NO extra arms, deformed hand, mutated hand, bad anatomy, disfigured hand, malformed fingers, extra digits, missing digits, amputated hand, extra limbs, body horror, clipping artifacts.";

/** 美甲场景固定后缀（原有，保持向后兼容）。 */
export const AI_IMAGE_SCENE_SUFFIX =
  "nail art design on fingernails, manicure, close-up hand photo, beautiful, high detail";

/**
 * 前置手数量约束（简短、醒目）。部分生图模型对提示词开头的约束更敏感，
 * 因此在用户提示词之前注入一句最短的手数量与手指数约束；完整约束仍附在末尾。
 */
export const HAND_COUNT_PREFIX =
  "画面中只能出现一只手（单手场景）或最多两只手（双手场景），绝对禁止第三只手；每只手恰好五根手指，不多不少。以下内容为主题描述：";

/**
 * 组装发送给生图模型的完整提示词：
 * 前置手数量约束 → 用户提示词 → 美甲场景后缀 → 隐藏系统提示词（用户不可见）。
 */
export function assembleAiImagePrompt(userPrompt: string): string {
  return `${HAND_COUNT_PREFIX}${userPrompt}, ${AI_IMAGE_SCENE_SUFFIX}. ${HAND_ANATOMY_SYSTEM_PROMPT}`;
}
