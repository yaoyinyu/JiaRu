import assert from "node:assert/strict";
import test from "node:test";

import { analyzeHandProfile } from "../src/lib/nail-personalization/hand-profile.ts";
import type { NailTextureCandidate } from "../src/lib/nail-texture-recognition/types.ts";
import type { FingerIndex } from "../src/lib/nail-personalization/types.ts";

function candidate(overrides: Partial<NailTextureCandidate> = {}): NailTextureCandidate {
  return {
    id: overrides.id ?? "c",
    cx: 0,
    cy: 0,
    length: 70,
    width: 60,
    angle: Math.PI / 2,
    score: 0.9,
    confidence: "high",
    source: "model",
    suggestedFinger: null,
    ...overrides,
  };
}

/** 五指横向排布（跨指方向为 x），指甲长轴竖直（angle = π/2）。 */
function rowCandidates(
  length: number,
  width: number,
  overrides?: (index: number) => Partial<NailTextureCandidate>
): NailTextureCandidate[] {
  return [0, 1, 2, 3, 4].map((index) =>
    candidate({
      id: `row-${index}`,
      cx: index * 50,
      cy: 0,
      length,
      width,
      angle: Math.PI / 2,
      suggestedFinger: index as FingerIndex,
      ...(overrides ? overrides(index) : {}),
    })
  );
}

/** 五指纵向排布（沿指方向为 y），指甲长轴竖直。 */
function columnCandidates(length: number, width: number): NailTextureCandidate[] {
  return [0, 1, 2, 3, 4].map((index) =>
    candidate({
      id: `col-${index}`,
      cx: 0,
      cy: index * 50,
      length,
      width,
      angle: Math.PI / 2,
      suggestedFinger: index as FingerIndex,
    })
  );
}

test("短宽排布判定为 wide-short", () => {
  const profile = analyzeHandProfile(rowCandidates(70, 60));
  assert.equal(profile.shape, "wide-short");
  assert.equal(profile.shapeSource, "classified");
  assert.ok(profile.medianNailAspect < 1.25);
  assert.ok((profile.palmAspect ?? 0) > 0.72);
});

test("长窄排布判定为 narrow-long", () => {
  const profile = analyzeHandProfile(columnCandidates(100, 50));
  assert.equal(profile.shape, "narrow-long");
  assert.ok(profile.medianNailAspect > 1.55);
  assert.ok((profile.palmAspect ?? 1) < 0.62);
});

test("拇指相对宽且甲面偏长判定为 slim-tapered", () => {
  const profile = analyzeHandProfile(rowCandidates(90, 60));
  assert.equal(profile.shape, "slim-tapered");
  assert.ok((profile.thumbRatio ?? 0) > 0.78);
});

test("比例居中且无强特征时回落 balanced", () => {
  const profile = analyzeHandProfile(
    rowCandidates(100, 74, (index) => (index === 0 ? { width: 50 } : {}))
  );
  assert.equal(profile.shape, "balanced");
  assert.equal(profile.shapeSource, "classified");
});

test("手斜置（旋转 30°/90°）分类结果与正视一致（手轴归一化生效）", () => {
  const upright = analyzeHandProfile(rowCandidates(70, 60));
  for (const rotation of [Math.PI / 6, Math.PI / 2]) {
    const rotated = rowCandidates(70, 60).map((item) => {
      const cos = Math.cos(rotation);
      const sin = Math.sin(rotation);
      return {
        ...item,
        cx: item.cx * cos - item.cy * sin,
        cy: item.cx * sin + item.cy * cos,
        angle: item.angle + rotation,
      };
    });
    const profile = analyzeHandProfile(rotated);
    assert.equal(profile.shape, upright.shape, `rotation=${rotation}`);
    assert.ok(
      Math.abs((profile.palmAspect ?? 0) - (upright.palmAspect ?? 0)) < 1e-6,
      `rotation=${rotation} palmAspect 漂移`
    );
  }
});

test("候选不足 3 时 completeness 低、出警告且不做手轴归一化", () => {
  const profile = analyzeHandProfile(rowCandidates(70, 60).slice(0, 2));
  assert.ok(profile.completeness < 0.6, `completeness=${profile.completeness}`);
  assert.ok(profile.warnings.includes("hand_profile_insufficient_candidates"));
  assert.ok(profile.warnings.includes("hand_profile_axis_unknown"));
  assert.equal(profile.palmAspect, null);
});

test("零尺寸与异常长宽比候选被过滤", () => {
  const profile = analyzeHandProfile([
    ...rowCandidates(70, 60),
    candidate({ id: "zero", length: 0, width: 10 }),
    candidate({ id: "weird", length: 500, width: 10, cx: 500, cy: 0 }),
  ]);
  assert.equal(profile.nailBeds.length, 5);
  assert.ok(profile.warnings.includes("hand_profile_invalid_candidates_dropped"));
});

test("重复甲面只保留得分较高者", () => {
  const profile = analyzeHandProfile([
    candidate({ id: "a", cx: 25, cy: 0, score: 0.9, suggestedFinger: 0 }),
    candidate({ id: "b", cx: 27, cy: 1, score: 0.5, suggestedFinger: 0 }),
    ...rowCandidates(70, 60).slice(1),
  ]);
  assert.equal(profile.duplicateCandidates, 1);
  assert.ok(profile.warnings.includes("hand_profile_duplicate_candidates"));
  assert.ok(profile.nailBeds.every((bed) => bed.lengthPx === 70));
});

test("suggestedFinger 全为 null 时 slim-tapered 不可命中且标记来源为不可判定", () => {
  const profile = analyzeHandProfile(rowCandidates(90, 60).map((item) => ({
    ...item,
    suggestedFinger: null,
  })));
  assert.notEqual(profile.shape, "slim-tapered");
  assert.ok(profile.warnings.includes("hand_profile_thumb_unknown"));
  assert.equal(profile.shapeSource, "insufficient-evidence");
});

test("无候选时输出空 profile 且 completeness 为 0", () => {
  const profile = analyzeHandProfile([]);
  assert.equal(profile.nailBeds.length, 0);
  assert.equal(profile.completeness, 0);
  assert.ok(profile.warnings.includes("hand_profile_no_valid_candidates"));
});
