/**
 * AI 生图输出尺寸与画面比例（宽高比）共享定义。
 *
 * 与 Agnes Image 2.1 Flash 技术文档「尺寸与宽高比」「输出尺寸参考」保持一致：
 * - 尺寸档位 size：`1K`、`2K`、`3K`、`4K`（推荐档位式写法）。
 * - 画面比例 ratio：`1:1`、`3:4`、`4:3`、`16:9`、`9:16`、`2:3`、`3:2`、`21:9`（默认 `1:1`）。
 * - 期望的可预期输出尺寸由「尺寸档位 + 画面比例」组合决定（见 AI_IMAGE_SIZE_TABLE）。
 *
 * 该模块被前端页面（展示可选尺寸/比例与最终像素尺寸）与服务端路由（校验白名单）
 * 共同引用，因此不得引入任何服务端专属代码（如 process.env、fetch）。
 */

export const AI_IMAGE_SIZES = ["1K", "2K", "3K", "4K"] as const;
export type AiImageSize = (typeof AI_IMAGE_SIZES)[number];

export const AI_IMAGE_RATIOS = [
  "1:1",
  "3:4",
  "4:3",
  "16:9",
  "9:16",
  "2:3",
  "3:2",
  "21:9",
] as const;
export type AiImageRatio = (typeof AI_IMAGE_RATIOS)[number];

/** 默认尺寸档位。 */
export const DEFAULT_AI_IMAGE_SIZE: AiImageSize = "1K";
/** 默认画面比例。 */
export const DEFAULT_AI_IMAGE_RATIO: AiImageRatio = "1:1";

/**
 * 输出尺寸参考表（横向档位 × 纵向比例），数值取自 Agnes Image 2.1 Flash 技术文档。
 * 键为 `size:ratio`，值为最终像素尺寸字符串（如 "2048x2048"）。
 */
export const AI_IMAGE_SIZE_TABLE: Record<
  AiImageSize,
  Record<AiImageRatio, string>
> = {
  "1K": {
    "1:1": "1024x1024",
    "3:4": "864x1152",
    "4:3": "1152x864",
    "16:9": "1312x736",
    "9:16": "736x1312",
    "2:3": "832x1248",
    "3:2": "1248x832",
    "21:9": "1568x672",
  },
  "2K": {
    "1:1": "2048x2048",
    "3:4": "1728x2304",
    "4:3": "2304x1728",
    "16:9": "2624x1472",
    "9:16": "1472x2624",
    "2:3": "1664x2496",
    "3:2": "2496x1664",
    "21:9": "3136x1344",
  },
  "3K": {
    "1:1": "3072x3072",
    "3:4": "2592x3456",
    "4:3": "3456x2592",
    "16:9": "3936x2208",
    "9:16": "2208x3936",
    "2:3": "2496x3744",
    "3:2": "3744x2496",
    "21:9": "4704x2016",
  },
  "4K": {
    "1:1": "4096x4096",
    "3:4": "3456x4608",
    "4:3": "4608x3456",
    "16:9": "5248x2944",
    "9:16": "2944x5248",
    "2:3": "3328x4992",
    "3:2": "4992x3328",
    "21:9": "6272x2688",
  },
};

/** 是否合法的尺寸档位。 */
export function isAiImageSize(value: unknown): value is AiImageSize {
  return typeof value === "string" && AI_IMAGE_SIZES.includes(value as AiImageSize);
}

/** 是否合法的画面比例。 */
export function isAiImageRatio(value: unknown): value is AiImageRatio {
  return typeof value === "string" && AI_IMAGE_RATIOS.includes(value as AiImageRatio);
}

/** 尺寸档位 + 画面比例 → 最终输出像素尺寸（如 "1024x1024"）。 */
export function resolveAiImageDimension(
  size: AiImageSize,
  ratio: AiImageRatio
): string {
  return AI_IMAGE_SIZE_TABLE[size][ratio];
}
