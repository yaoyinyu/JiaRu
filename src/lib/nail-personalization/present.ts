import type {
  HandProfile,
  NailHealthHeuristic,
  Recommendation,
  SkinToneAnalysis,
} from "./types.ts";
import { describeLength, describeShape } from "./rules.ts";

export interface PresentationStat {
  label: string;
  value: string;
}

export interface PresentationSummary {
  severity: "ok" | "review" | "info";
  title: string;
  messages: string[];
  stats?: PresentationStat[];
}

const ITA_BAND_LABEL: Record<SkinToneAnalysis["itaBand"], string> = {
  "very-light": "极浅",
  light: "偏浅",
  intermediate: "中等",
  tan: "偏深",
  brown: "深",
  dark: "很深",
};

const UNDERTONE_LABEL: Record<SkinToneAnalysis["undertone"], string> = {
  warm: "暖调",
  cool: "冷调",
  neutral: "中性",
  olive: "橄榄调",
};

const HAND_SHAPE_LABEL: Record<HandProfile["shape"], string> = {
  "narrow-long": "纤长型",
  "wide-short": "短宽型",
  "slim-tapered": "收窄修长型",
  balanced: "均衡型",
};

export const WARNING_MESSAGES: Record<string, string> = {
  auxiliary_analysis_notice:
    "当前为辅助定位结果，甲面边界未经正式模型确认；分析结论仅供参考，请结合实物效果判断。",
  skin_sampling_low_quality: "肤色采样点不足或质量偏低，已隐藏肤色分析结果而不是给出猜测值。",
  ita_band_unreliable_low_chroma:
    "本次肤色的黄蓝通道接近中性，深浅分档在非受控拍摄下不可靠，已不再按肤色深浅推荐颜色。",
  ita_band_unreliable_near_boundary:
    "本次肤色的深浅分档接近档位边界，换一个光环境可能落到相邻档，已不再按肤色深浅推荐颜色。",
  skin_sampling_no_candidates: "没有可用的甲面候选，无法进行甲周肤色采样。",
  nail_health_requires_mask: "当前候选没有像素级甲面 mask，指甲健康观察不可用（已隐藏而非展示猜测值）。",
  nail_health_insufficient_foreground: "甲面前景像素过少，健康观察结果仅供粗略参考。",
  nail_health_axis_unknown: "缺少甲面朝向信息，条纹指标按默认轴向计算。",
  hand_profile_insufficient_candidates: "可用甲面候选不足，手型与甲床比例仅供参考。",
  hand_profile_axis_unknown: "可用候选不足或缺少朝向信息，未做手轴归一化，掌心跨度近似不可用。",
  hand_profile_thumb_unknown: "未识别到拇指甲面，收窄修长型判定不可用。",
  hand_profile_duplicate_candidates: "检测到重复甲面候选，已按得分保留唯一一个。",
  hand_profile_no_valid_candidates: "没有几何有效的甲面候选。",
  hand_profile_invalid_candidates_dropped: "部分候选几何异常（零尺寸或长宽比越界），已剔除。",
  skin_tone_unavailable_color_fallback: "肤色不可用，颜色建议已降级为场合与风格规则。",
  no_candidates_no_recommendation: "未能定位到甲面，未生成任何推荐。请重新拍摄五指清晰、光照均匀的照片。",
  preset_overridden_by_gallery: "同时传入了灵感参数，已沿用灵感预涂色。",
};

export function describeWarning(code: string): string {
  return WARNING_MESSAGES[code] ?? "分析结果存在未分类提示，请结合实物效果判断。";
}

/**
 * 提示去重：warning code 是唯一去重键。
 * 调用方需按呈现优先级（notices > explanation > profile.warnings）**依次传入**，
 * 本函数保留首次出现者，保证同一 code 在最终呈现中只出现一次。
 */
export function dedupeWarnings(codes: readonly string[]): string[] {
  return [...new Set(codes.filter((code) => typeof code === "string" && code.length > 0))];
}

export function summarizeSkinTone(skin: SkinToneAnalysis | null): PresentationSummary | null {
  if (!skin) return null;
  const sourceNote = skin.undertoneSource === "self-reported"
    ? "底调取自你的自评，未使用测量值。"
    : "底调为照片测得，非受控拍摄仅供参考。";
  const messages = [
    `测得 ITA° ${skin.ita.toFixed(1)}（${ITA_BAND_LABEL[skin.itaBand]}），底调为${UNDERTONE_LABEL[skin.undertone]}。`,
    sourceNote,
    "ITA° 为非受控拍摄下的估计值，仅供色号筛选参考。",
  ];
  if (!skin.itaReliable) {
    messages.push(
      skin.itaUncertainty === "low-chroma"
        ? "肤色黄蓝通道接近中性，深浅分档不可靠，本次颜色建议未按肤色深浅给出。"
        : "深浅分档接近档位边界，换一个光环境可能落到相邻档，本次颜色建议未按肤色深浅给出。"
    );
  }
  return {
    severity: skin.itaReliable ? "ok" : "review",
    title: "肤色与底调",
    messages,
    stats: [
      { label: "L*", value: skin.lab.L.toFixed(1) },
      { label: "a*", value: skin.lab.a.toFixed(1) },
      { label: "b*", value: skin.lab.b.toFixed(1) },
      { label: "采样点", value: String(skin.sampleCount) },
      { label: "采样质量", value: skin.quality.toFixed(2) },
    ],
  };
}

export function summarizeHandProfile(profile: HandProfile): PresentationSummary {
  const messages = [
    `手型判读：${HAND_SHAPE_LABEL[profile.shape]}（甲床长宽比中位数 ${profile.medianNailAspect.toFixed(2)}）。`,
  ];
  if (profile.shapeSource === "insufficient-evidence") {
    messages.push("关键几何量不足，本次未能确认手型，以上仅为回落值，不代表已确认为均衡型。");
  }
  messages.push("手型为由甲面候选派生的近似比例，识别链路不含掌部关键点。");
  return {
    severity: profile.shapeSource === "insufficient-evidence" ? "review" : "ok",
    title: "手型与甲床比例",
    messages,
    stats: [
      { label: "甲面数", value: String(profile.nailBeds.length) },
      { label: "完整度", value: profile.completeness.toFixed(2) },
      { label: "掌心跨度近似", value: profile.palmAspect === null ? "不可用" : profile.palmAspect.toFixed(2) },
      { label: "拇指比", value: profile.thumbRatio === null ? "不可用" : profile.thumbRatio.toFixed(2) },
    ],
  };
}

export function summarizeNailHealth(health: NailHealthHeuristic | null): PresentationSummary | null {
  if (!health) return null;
  return {
    severity: "info",
    title: "指甲健康观察",
    messages: [
      `启发式观察得分 ${health.score}/100：颜色均匀度 ${health.colorUniformity.toFixed(2)}、高光占比 ${health.highlightRatio.toFixed(2)}、条纹指标 ${health.textureStreaking.toFixed(2)}。`,
      "启发式观察，不构成医疗或诊断结论。",
    ],
  };
}

export function presentRecommendation(rec: Recommendation): PresentationSummary {
  const confidenceLabel = rec.confidence === "high" ? "高" : rec.confidence === "medium" ? "中" : "低";
  const messages = [
    `${describeShape(rec.shape)} · ${describeLength(rec.length)} · ${rec.colors.family}（${rec.colors.presetNames.join("、")}）`,
    ...rec.explanations.map((explanation) => explanation.message),
    `置信度：${confidenceLabel}${rec.requiresManualConfirmation ? "（需人工确认）" : ""}。`,
  ];
  return {
    severity: rec.requiresManualConfirmation ? "review" : "ok",
    title: `推荐 ${rec.rank}`,
    messages,
    stats: [
      { label: "组合分", value: rec.score.toFixed(2) },
      { label: "命中规则", value: rec.ruleHits.join("、") },
    ],
  };
}

/**
 * 与既有 auxiliaryDetectionNotice 同构的页面级声明。
 * 仅 fallback 返回文案；model 返回 null。
 */
export function auxiliaryAnalysisNotice(
  backend: "model" | "fallback",
  candidateCount: number
): string | null {
  if (backend !== "fallback") return null;
  const status = "当前为辅助定位结果，甲面边界未经正式模型确认。";
  return status + (candidateCount > 0
    ? `已找到 ${candidateCount} 个候选甲面，分析结论仅供参考，请结合实物效果判断。`
    : "未能定位到候选甲面，请在图片上手动添加完整甲面后再分析。");
}
