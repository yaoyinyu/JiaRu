/**
 * Seedream（火山方舟）生图输出尺寸共享定义。
 *
 * 与火山方舟《图片生成 API》文档的尺寸映射表保持一致：
 * - Seedream 5.0 pro（图片生成场景）：档位 `1K`、`1.5K`、`2K`（无 3K/4K）。
 * - Seedream 5.0 lite：档位 `2K`、`3K`、`4K`（无 1K）。
 * - Ark 接口没有独立 ratio 参数，宽高比通过"方式 2：显式宽高像素值"表达，
 *   因此本模块提供「档位 × 画面比例 → WxH 像素串」的确定性换算表。
 *
 * 该模块被前端页面（展示可选档位/比例与最终像素尺寸）与服务端路由（校验白名单）
 * 共同引用，因此不得引入任何服务端专属代码（如 process.env、fetch）。
 */

import type { AiImageRatio } from "./ai-image-size.ts";

/** Seedream 模型类别（pro = 5.0 pro，lite = 5.0 lite）。 */
export const SEEDREAM_MODELS = ["pro", "lite"] as const;
export type SeedreamModel = (typeof SEEDREAM_MODELS)[number];

/** Seedream 5.0 pro 支持的尺寸档位。 */
export const SEEDREAM_PRO_SIZES = ["1K", "1.5K", "2K"] as const;
export type SeedreamProSize = (typeof SEEDREAM_PRO_SIZES)[number];

/** Seedream 5.0 lite 支持的尺寸档位。 */
export const SEEDREAM_LITE_SIZES = ["2K", "3K", "4K"] as const;
export type SeedreamLiteSize = (typeof SEEDREAM_LITE_SIZES)[number];

/** 各模型默认尺寸档位（pro 文档默认 2K；lite 文档默认 2048x2048，即 2K）。 */
export const DEFAULT_SEEDREAM_SIZE: Record<SeedreamModel, string> = {
  pro: "2K",
  lite: "2K",
};

/**
 * Seedream 5.0 pro「档位 × 比例 → 宽高像素值」换算表。
 * 数值取自火山方舟文档中 pro 模型的分辨率映射参考值。
 */
export const SEEDREAM_PRO_SIZE_TABLE: Record<
  SeedreamProSize,
  Record<AiImageRatio, string>
> = {
  "1K": {
    "1:1": "1024x1024",
    "3:4": "864x1152",
    "4:3": "1152x864",
    "16:9": "1424x800",
    "9:16": "800x1424",
    "2:3": "832x1248",
    "3:2": "1248x832",
    "21:9": "1568x672",
  },
  "1.5K": {
    "1:1": "1536x1536",
    "3:4": "1344x1792",
    "4:3": "1792x1344",
    "16:9": "2048x1152",
    "9:16": "1152x2048",
    "2:3": "1248x1872",
    "3:2": "1872x1248",
    "21:9": "2352x1008",
  },
  "2K": {
    "1:1": "2048x2048",
    "3:4": "1776x2368",
    "4:3": "2368x1776",
    "16:9": "2816x1584",
    "9:16": "1584x2816",
    "2:3": "1664x2496",
    "3:2": "2496x1664",
    "21:9": "3136x1344",
  },
};

/**
 * Seedream 5.0 lite「档位 × 比例 → 宽高像素值」换算表。
 * 数值取自火山方舟文档中 lite 模型的分辨率映射参考值。
 */
export const SEEDREAM_LITE_SIZE_TABLE: Record<
  SeedreamLiteSize,
  Record<AiImageRatio, string>
> = {
  "2K": {
    "1:1": "2048x2048",
    "3:4": "1728x2304",
    "4:3": "2304x1728",
    "16:9": "2848x1600",
    "9:16": "1600x2848",
    "2:3": "1664x2496",
    "3:2": "2496x1664",
    "21:9": "3136x1344",
  },
  "3K": {
    "1:1": "3072x3072",
    "3:4": "2592x3456",
    "4:3": "3456x2592",
    "16:9": "4096x2304",
    "9:16": "2304x4096",
    "2:3": "2496x3744",
    "3:2": "3744x2496",
    "21:9": "4704x2016",
  },
  "4K": {
    "1:1": "4096x4096",
    "3:4": "3520x4704",
    "4:3": "4704x3520",
    "16:9": "5504x3040",
    "9:16": "3040x5504",
    "2:3": "3328x4992",
    "3:2": "4992x3328",
    "21:9": "6240x2656",
  },
};

/** 指定模型支持的尺寸档位列表。 */
export function seedreamSizesFor(model: SeedreamModel): readonly string[] {
  return model === "pro" ? SEEDREAM_PRO_SIZES : SEEDREAM_LITE_SIZES;
}

/** 是否为该模型合法的尺寸档位。 */
export function isSeedreamSize(
  model: SeedreamModel,
  value: unknown
): value is string {
  return (
    typeof value === "string" &&
    (seedreamSizesFor(model) as readonly string[]).includes(value)
  );
}

/** 是否为合法的 Seedream 模型类别。 */
export function isSeedreamModel(value: unknown): value is SeedreamModel {
  return (
    typeof value === "string" &&
    (SEEDREAM_MODELS as readonly string[]).includes(value)
  );
}

/**
 * 「模型 + 档位 + 比例」→ 显式宽高像素串（如 "2048x2048"）。
 * 仅当 model/size/ratio 均合法时返回结果，否则返回 null（由调用方转为 400）。
 */
export function resolveSeedreamDimension(
  model: SeedreamModel,
  size: string,
  ratio: string
): string | null {
  if (!isSeedreamSize(model, size)) return null;
  if (model === "pro") {
    const table = SEEDREAM_PRO_SIZE_TABLE[size as SeedreamProSize];
    return table[ratio as AiImageRatio] ?? null;
  }
  const table = SEEDREAM_LITE_SIZE_TABLE[size as SeedreamLiteSize];
  return table[ratio as AiImageRatio] ?? null;
}
