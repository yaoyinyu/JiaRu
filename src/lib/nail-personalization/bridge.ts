import { PRESET_COLORS } from "../utils.ts";
import type { NailShapeAdvice, Recommendation } from "./types.ts";

/** 甲型白名单，与 types.ts 的 NailShapeAdvice 保持一致。 */
export const NAIL_SHAPE_WHITELIST: readonly NailShapeAdvice[] = [
  "round",
  "squoval",
  "square",
  "oval",
  "almond",
  "coffin",
  "stiletto",
];

export interface AnalysisBridgeParams {
  preset: string;
  shape: string;
}

export type ParsedAnalysisBridgeParams =
  | { ok: true; preset: string; shape: NailShapeAdvice }
  | { ok: false };

const PRESET_NAMES: ReadonlySet<string> = new Set(PRESET_COLORS.map((item) => item.name));

/**
 * 出站参数：preset 取推荐色系的首个预设色名（必须存在于 PRESET_COLORS），
 * shape 透传甲型建议（v1 编辑器不消费，仅随链接携带）。
 */
export function buildAnalysisBridgeParams(rec: Recommendation): AnalysisBridgeParams {
  const preset = rec.colors.presetNames.find((name) => PRESET_NAMES.has(name))
    ?? PRESET_COLORS[0].name;
  return { preset, shape: rec.shape };
}

/** 入站解析：任一字段非法即返回 { ok: false }，调用方降级为普通跳转，不抛错。 */
export function parseAnalysisBridgeParams(params: {
  preset?: string | null;
  shape?: string | null;
}): ParsedAnalysisBridgeParams {
  const preset = params.preset;
  const shape = params.shape;
  if (!preset || !PRESET_NAMES.has(preset)) return { ok: false };
  if (!shape || !NAIL_SHAPE_WHITELIST.includes(shape as NailShapeAdvice)) return { ok: false };
  return { ok: true, preset, shape: shape as NailShapeAdvice };
}
