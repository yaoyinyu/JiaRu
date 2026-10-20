import assert from "node:assert/strict";
import test from "node:test";

import { analyzeNailPersonalization } from "../src/lib/nail-personalization/index.ts";
import { auxiliaryAnalysisNotice, describeWarning } from "../src/lib/nail-personalization/present.ts";
import type { NailTextureCandidate } from "../src/lib/nail-texture-recognition/types.ts";
import type { OriginalImagePixels, UserScenario } from "../src/lib/nail-personalization/types.ts";

const SKIN: [number, number, number] = [220, 180, 160];

function makeImage(width: number, height: number): OriginalImagePixels {
  const data = new Uint8ClampedArray(width * height * 4);
  for (let index = 0; index < width * height; index += 1) {
    const offset = index * 4;
    data[offset] = SKIN[0];
    data[offset + 1] = SKIN[1];
    data[offset + 2] = SKIN[2];
    data[offset + 3] = 255;
  }
  return { width, height, data, pixelSource: "original" };
}

function candidates(): NailTextureCandidate[] {
  return [0, 1, 2, 3, 4].map((index) => ({
    id: `c${index}`,
    cx: 60 + index * 100,
    cy: 210,
    length: 90,
    width: 60,
    angle: Math.PI / 2,
    score: 0.9,
    confidence: "high" as const,
    source: "partial-closeup" as const,
    suggestedFinger: index,
  }));
}

const scenario: UserScenario = { occasion: "wedding", style: "elegant" };

test("端到端：合成输入产出完整 PersonalizationResult", () => {
  const result = analyzeNailPersonalization({
    image: makeImage(520, 420),
    candidates: candidates(),
    backend: "fallback",
    scenario,
  });

  assert.equal(result.noCandidates, false);
  assert.equal(result.handProfile.shape, "slim-tapered");
  assert.ok(result.handProfile.nailBeds.length === 5);
  assert.ok(result.skinTone, "肤色采样应可用");
  assert.ok((result.skinTone?.sampleCount ?? 0) >= 120);
  assert.equal(result.skinTone?.undertoneSource, "measured");
  // 该 fixture 的 ITA° 为 59.2626…，距 55 边界 4.26°，应判可靠（黄金值，防阈值漂移）。
  assert.ok(Math.abs((result.skinTone?.ita ?? 0) - 59.2626) < 0.01);
  assert.equal(result.skinTone?.itaReliable, true);
  assert.equal(result.skinTone?.itaUncertainty, undefined);
  assert.equal(result.nailHealth, null, "无 mask 候选时健康通道应为 null");
  assert.equal(result.recommendations.length, 3);
  for (const rec of result.recommendations) {
    assert.equal(rec.requiresManualConfirmation, true);
    assert.ok(rec.explanations.length > 0);
  }
  assert.ok(result.notices.includes("nail_health_requires_mask"));
  assert.ok(result.notices.includes("auxiliary_analysis_notice"));
  assert.ok(describeWarning("auxiliary_analysis_notice").includes("未经正式模型确认"));
});

test("0 候选时不产出任何推荐且标记为未定位", () => {
  const result = analyzeNailPersonalization({
    image: makeImage(520, 420),
    candidates: [],
    backend: "fallback",
    scenario,
  });
  assert.equal(result.noCandidates, true);
  assert.deepEqual(result.recommendations, []);
  assert.equal(result.skinTone, null);
  assert.equal(result.nailHealth, null);
  assert.ok(result.notices.includes("no_candidates_no_recommendation"));
});

test("model 后端不附加辅助定位声明", () => {
  const result = analyzeNailPersonalization({
    image: makeImage(520, 420),
    candidates: candidates(),
    backend: "model",
    scenario,
  });
  assert.equal(auxiliaryAnalysisNotice("model", 5), null);
  assert.ok(!result.notices.includes("auxiliary_analysis_notice"));
});

test("自评底调覆盖测量值并标记来源", () => {
  const result = analyzeNailPersonalization({
    image: makeImage(520, 420),
    candidates: candidates(),
    backend: "model",
    scenario: { ...scenario, selfReportedUndertone: "cool" },
  });
  assert.equal(result.skinTone?.undertone, "cool");
  assert.equal(result.skinTone?.undertoneSource, "self-reported");
});

test("琥珀声明文案与既有 auxiliaryDetectionNotice 同构（含人工确认语义）", () => {
  const notice = auxiliaryAnalysisNotice("fallback", 5);
  assert.ok(notice?.includes("辅助定位"));
  assert.ok(notice?.includes("人工确认") || notice?.includes("结合实物效果判断"));
});
