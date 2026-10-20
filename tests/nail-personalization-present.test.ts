import assert from "node:assert/strict";
import test from "node:test";

import {
  auxiliaryAnalysisNotice,
  dedupeWarnings,
  presentRecommendation,
  summarizeHandProfile,
  summarizeNailHealth,
  summarizeSkinTone,
} from "../src/lib/nail-personalization/present.ts";
import type {
  HandProfile,
  NailHealthHeuristic,
  Recommendation,
  SkinToneAnalysis,
} from "../src/lib/nail-personalization/types.ts";

const profile: HandProfile = {
  shape: "balanced",
  shapeSource: "classified",
  palmAspect: 0.9,
  thumbRatio: 0.9,
  nailBeds: [],
  medianNailAspect: 1.3,
  completeness: 1,
  duplicateCandidates: 0,
  warnings: [],
};

const skinTone: SkinToneAnalysis = {
  lab: { L: 65, a: 5, b: 12 },
  ita: 45,
  itaBand: "light",
  itaReliable: true,
  monkGrade: 3,
  undertone: "warm",
  undertoneSource: "measured",
  sampleCount: 200,
  quality: 0.9,
  warnings: [],
};

const recommendation: Recommendation = {
  id: "round-short-职场裸色",
  rank: 1,
  score: 1,
  shape: "round",
  length: "short",
  colors: { family: "职场裸色", presetNames: ["裸粉色", "裸色", "奶茶色"] },
  explanations: [{ ruleId: "occasion-work-nude", message: "职场通勤选裸色系最稳。", severity: "info" }],
  confidence: "medium",
  requiresManualConfirmation: true,
  ruleHits: ["occasion-work-nude"],
};

test("skin/health 为 null 时摘要返回 null（隐藏而非猜测）", () => {
  assert.equal(summarizeSkinTone(null), null);
  assert.equal(summarizeNailHealth(null), null);
});

test("肤色摘要区分测得与自评，并注明非受控拍摄", () => {
  const measured = summarizeSkinTone(skinTone);
  assert.ok(measured);
  assert.ok(measured.messages.some((item) => item.includes("照片测得")));
  assert.ok(measured.messages.some((item) => item.includes("非受控拍摄")));
  assert.equal(measured.severity, "ok");
  assert.equal(measured.stats?.length, 5);

  const selfReported = summarizeSkinTone({ ...skinTone, undertoneSource: "self-reported" });
  assert.ok(selfReported?.messages.some((item) => item.includes("自评")));
});

test("ITA° 分档不可靠时摘要降级为 review 并说明未按深浅推荐", () => {
  for (const reason of ["low-chroma", "near-boundary"] as const) {
    const summary = summarizeSkinTone({ ...skinTone, itaReliable: false, itaUncertainty: reason });
    assert.ok(summary);
    assert.equal(summary.severity, "review");
    assert.ok(summary.messages.some((item) => item.includes("未按肤色深浅给出")));
  }
});

test("手型不可判定时 severity 为 review 并说明不代表已确认", () => {
  const ok = summarizeHandProfile(profile);
  assert.equal(ok.severity, "ok");

  const unknown = summarizeHandProfile({ ...profile, shapeSource: "insufficient-evidence" });
  assert.equal(unknown.severity, "review");
  assert.ok(unknown.messages.some((item) => item.includes("不代表已确认为均衡型")));
});

test("健康摘要恒含非医疗声明", () => {
  const health: NailHealthHeuristic = {
    score: 88,
    colorUniformity: 0.9,
    highlightRatio: 0.1,
    textureStreaking: 0.05,
    warnings: [],
    heuristicOnly: true,
  };
  const summary = summarizeNailHealth(health);
  assert.ok(summary);
  assert.ok(summary.messages.some((item) => item.includes("不构成医疗或诊断结论")));
  assert.equal(summary.severity, "info");
});

test("推荐摘要带解释与置信度，需人工确认时为 review", () => {
  const summary = presentRecommendation(recommendation);
  assert.equal(summary.severity, "review");
  assert.ok(summary.messages.some((item) => item.includes("需人工确认")));
  assert.ok(summary.messages.some((item) => item.includes("职场通勤选裸色系最稳。")));

  const confident = presentRecommendation({ ...recommendation, requiresManualConfirmation: false, confidence: "high" });
  assert.equal(confident.severity, "ok");
});

test("dedupeWarnings 同一 code 只保留一处且保持传入顺序", () => {
  const deduped = dedupeWarnings([
    "skin_sampling_low_quality",
    "hand_profile_thumb_unknown",
    "skin_sampling_low_quality",
    "",
    "hand_profile_thumb_unknown",
  ]);
  assert.deepEqual(deduped, ["skin_sampling_low_quality", "hand_profile_thumb_unknown"]);
});

test("auxiliaryAnalysisNotice：model 返回 null，fallback 按候选数给不同文案", () => {
  assert.equal(auxiliaryAnalysisNotice("model", 5), null);
  const withCandidates = auxiliaryAnalysisNotice("fallback", 5);
  assert.ok(withCandidates?.includes("辅助定位"));
  assert.ok(withCandidates?.includes("5"));
  const withoutCandidates = auxiliaryAnalysisNotice("fallback", 0);
  assert.ok(withoutCandidates?.includes("手动添加"));
});
