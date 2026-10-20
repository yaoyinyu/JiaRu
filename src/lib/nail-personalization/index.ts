import type { NailTextureCandidate } from "../nail-texture-recognition/types.ts";
import {
  approximateMonkGrade,
  classifyItaBandStable,
  classifyUndertone,
  individualTypologyAngle,
} from "./color-science.ts";
import { analyzeHandProfile } from "./hand-profile.ts";
import { analyzeNailHealthHeuristic } from "./nail-health.ts";
import { auxiliaryAnalysisNotice, dedupeWarnings } from "./present.ts";
import { recommend } from "./rules.ts";
import {
  MIN_SKIN_SAMPLES,
  MIN_SKIN_SAMPLES_SINGLE_CANDIDATE,
  samplePeriNailSkin,
  SKIN_QUALITY_MIN,
} from "./skin-sampling.ts";
import type {
  PersonalizationInput,
  PersonalizationResult,
  SkinToneAnalysis,
} from "./types.ts";

const DEFAULT_EXPECTED_CANDIDATES = 5;

function hasLowConfidence(candidates: readonly NailTextureCandidate[]): boolean {
  return candidates.some((candidate) => candidate.confidence === "low");
}

/**
 * 编排入口：识别输出 → 三路纯函数分析 → 规则引擎 → 结果。
 * 全部计算在本地完成，不引入任何上传通道。
 */
export function analyzeNailPersonalization(
  input: PersonalizationInput
): PersonalizationResult {
  const expectedCandidates = Math.max(1, input.maxCandidates ?? DEFAULT_EXPECTED_CANDIDATES);
  const { candidates, scenario, backend, image } = input;

  const handProfile = analyzeHandProfile(candidates, { expectedCandidates });
  const noticeCandidates: string[] = [];

  // 琥珀辅助定位声明：fallback 时恒为页面级提示（发布拦截项，不得省略）。
  if (auxiliaryAnalysisNotice(backend, candidates.length)) {
    noticeCandidates.push("auxiliary_analysis_notice");
  }

  if (candidates.length === 0) {
    return {
      handProfile,
      skinTone: null,
      nailHealth: null,
      recommendations: [],
      notices: dedupeWarnings([
        ...noticeCandidates,
        "no_candidates_no_recommendation",
        "skin_sampling_no_candidates",
        "nail_health_requires_mask",
      ]),
      noCandidates: true,
    };
  }

  const sample = samplePeriNailSkin(image, candidates, { expectedCandidates });
  const effectiveCandidates = candidates.filter(
    (candidate) => Number.isFinite(candidate.length) && candidate.length > 0
  ).length;
  const minSamples = effectiveCandidates <= 1
    ? MIN_SKIN_SAMPLES_SINGLE_CANDIDATE
    : MIN_SKIN_SAMPLES;

  let skinTone: SkinToneAnalysis | null = null;
  if (sample.sampleCount >= minSamples && sample.quality >= SKIN_QUALITY_MIN) {
    const ita = individualTypologyAngle(sample.lab);
    const measuredUndertone = classifyUndertone(sample.lab);
    const selfReported = scenario.selfReportedUndertone;
    // 自评底调覆盖测量值时，ITA° 分档仍按实测登记，但底调来源改为 self-reported；
    // 分档可靠性独立判定，不因自评而改变（自评只覆盖底调，不覆盖深浅档）。
    const classification = classifyItaBandStable(sample.lab);
    const uncertaintyWarning = classification.reliable
      ? []
      : [classification.reason === "low-chroma"
        ? "ita_band_unreliable_low_chroma"
        : "ita_band_unreliable_near_boundary"];
    skinTone = {
      lab: { L: sample.lab.L, a: sample.lab.a, b: sample.lab.b },
      ita,
      itaBand: classification.band,
      itaReliable: classification.reliable,
      ...(classification.reason ? { itaUncertainty: classification.reason } : {}),
      monkGrade: approximateMonkGrade(sample.lab),
      undertone: selfReported ?? measuredUndertone,
      undertoneSource: selfReported ? "self-reported" : "measured",
      sampleCount: sample.sampleCount,
      quality: sample.quality,
      warnings: [...sample.warnings, ...uncertaintyWarning],
    };
  } else {
    noticeCandidates.push("skin_sampling_low_quality", "skin_tone_unavailable_color_fallback");
  }

  const nailHealth = analyzeNailHealthHeuristic(image, candidates);
  if (!nailHealth) noticeCandidates.push("nail_health_requires_mask");

  const recommendations = recommend(handProfile, skinTone, scenario, {
    backend,
    hasLowConfidenceCandidate: hasLowConfidence(candidates),
  });

  const notices = dedupeWarnings([
    ...noticeCandidates,
    ...handProfile.warnings,
    ...(skinTone?.warnings ?? []),
    ...(nailHealth?.warnings ?? []),
  ]);

  return {
    handProfile,
    skinTone,
    nailHealth,
    recommendations,
    notices,
    noCandidates: false,
  };
}

export * from "./types.ts";
export * from "./color-science.ts";
export * from "./hand-profile.ts";
export * from "./nail-health.ts";
export * from "./skin-sampling.ts";
export * from "./rules.ts";
export * from "./present.ts";
export * from "./bridge.ts";
