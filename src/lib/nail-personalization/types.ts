import type { ImagePixels } from "../nail-image-detection.ts";
import type { NailTextureCandidate } from "../nail-texture-recognition/types.ts";

export type FingerIndex = 0 | 1 | 2 | 3 | 4; // 与 suggestedFinger 一致
export type HandShapeClass = "narrow-long" | "wide-short" | "slim-tapered" | "balanced";
export type ItaBand = "very-light" | "light" | "intermediate" | "tan" | "brown" | "dark";
export type MonkGrade = 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10;
export type Undertone = "warm" | "cool" | "neutral" | "olive";
export type Occasion = "work" | "party" | "wedding" | "date" | "vacation" | "daily";
export type StylePreference = "low-maintenance" | "natural" | "bold" | "elegant" | "trendy";
export type ManualLabor = "none" | "light" | "heavy";
export type LengthAdvice = "short" | "medium" | "long";
export type NailShapeAdvice = "round" | "squoval" | "square" | "oval" | "almond" | "coffin" | "stiletto";
export type NailCondition = "healthy" | "thin-soft" | "brittle" | "unknown";

export interface NailBedMetrics {
  finger: FingerIndex | null;
  lengthPx: number;
  widthPx: number;
  aspectRatio: number;
  relativeWidth: number;
}

/**
 * 手型结论的来源。`classified` 表示由阈值判定得出；
 * `insufficient-evidence` 表示关键几何量缺失（palmAspect/thumbRatio 为 null）而回落 balanced，
 * 二者输出值相同但语义不同，UI 与测试不得把后者当作"确认为均衡手型"。
 */
export type HandShapeSource = "classified" | "insufficient-evidence";

export interface HandProfile {
  shape: HandShapeClass;
  shapeSource: HandShapeSource;
  /** 手轴坐标系下的掌心跨度近似（候选不含掌部 landmarks，为近似量；已按候选 angle 中位数旋转归一化）。 */
  palmAspect: number | null;
  thumbRatio: number | null;
  nailBeds: NailBedMetrics[];
  medianNailAspect: number;
  completeness: number;
  /** 被重复甲面判据剔除的候选数，仅作诊断。 */
  duplicateCandidates: number;
  warnings: string[];
}

export interface SkinToneAnalysis {
  lab: { L: number; a: number; b: number };
  ita: number;
  itaBand: ItaBand;
  /**
   * ITA° 分档是否可靠。false 时（|b*| 接近 0 或距分档边界过近）消费该分档的
   * 颜色规则必须弃权，UI 必须明示；不得把不可靠分档当作硬事实使用。
   */
  itaReliable: boolean;
  itaUncertainty?: "low-chroma" | "near-boundary";
  monkGrade: MonkGrade;
  undertone: Undertone;
  undertoneSource: "measured" | "self-reported";
  sampleCount: number;
  quality: number;
  warnings: string[];
}

export interface NailHealthHeuristic {
  score: number;
  colorUniformity: number;
  highlightRatio: number;
  textureStreaking: number;
  warnings: string[];
  /** 恒定 true：仅启发式观察，不构成医疗或诊断结论。 */
  heuristicOnly: true;
}

export interface UserScenario {
  occasion: Occasion;
  style?: StylePreference;
  manualLabor?: ManualLabor;
  lengthPreference?: LengthAdvice;
  selfReportedUndertone?: Undertone;
  /** 甲面状况自评（对齐资料汇编 §3.4「指甲薄软先加固」与 §8 结论）。 */
  nailCondition?: NailCondition;
  /** 仅触发安全提示，不参与推荐打分（材料化学安全性超出 v1 范围）。 */
  hasAllergyHistory?: boolean;
}

/**
 * 三态语义（规则实现必须遵守，见 rules.ts 规则表注 1）：
 * 所有 optional 字段的「未填」一律表示 unknown，严禁把 undefined 当作否定值参与条件判断；
 * `x !== "long"` 之类的写法在 undefined 下恒为 true，属已知语义缺陷。
 */
export function isKnown<T>(value: T | undefined): value is T {
  return value !== undefined && value !== null;
}

export interface ColorAdvice {
  family: string;
  presetNames: string[];
  season?: "spring" | "summer" | "autumn" | "winter";
}

export interface RecommendationExplanation {
  ruleId: string;
  message: string;
  severity: "info" | "warning";
}

export interface Recommendation {
  /** 确定性派生：`${shape}-${length}-${colors.family}`，同一输入必得同一 id（黄金测试逐字断言的前提）。 */
  id: string;
  rank: number;
  score: number;
  shape: NailShapeAdvice;
  length: LengthAdvice;
  colors: ColorAdvice;
  explanations: RecommendationExplanation[];
  confidence: "high" | "medium" | "low";
  requiresManualConfirmation: boolean;
  ruleHits: string[];
}

/**
 * 原图像素标记类型：肤色采样与健康启发式必须吃**原分辨率**像素。
 * 识别用的降采样图（最长边 ≤800）与它同为 ImagePixels 结构，类型层无法区分，
 * 因此用交叉类型强制调用方显式声明，防止误把 800 图当原图采样。
 */
export type OriginalImagePixels = ImagePixels & { readonly pixelSource: "original" };

export interface PersonalizationInput {
  image: OriginalImagePixels;
  candidates: readonly NailTextureCandidate[];
  backend: "model" | "fallback";
  scenario: UserScenario;
  /** 期望候选数（默认 5），用于 completeness 与 skin quality 分母。 */
  maxCandidates?: number;
}

export interface PersonalizationResult {
  handProfile: HandProfile;
  skinTone: SkinToneAnalysis | null;
  nailHealth: NailHealthHeuristic | null;
  recommendations: Recommendation[];
  notices: string[];
  /** 0 候选或识别失败时为 true：此时 recommendations 必为空，不计为一次成功分析。 */
  noCandidates: boolean;
}
