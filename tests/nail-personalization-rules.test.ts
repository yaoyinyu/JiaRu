import assert from "node:assert/strict";
import test from "node:test";

import { COLOR_RULES, NAIL_SHAPE_RULES, recommend } from "../src/lib/nail-personalization/rules.ts";
import { PRESET_COLORS } from "../src/lib/utils.ts";
import type {
  HandProfile,
  SkinToneAnalysis,
  UserScenario,
} from "../src/lib/nail-personalization/types.ts";

function profile(overrides: Partial<HandProfile> = {}): HandProfile {
  return {
    shape: "balanced",
    shapeSource: "classified",
    palmAspect: 0.9,
    thumbRatio: 0.9,
    nailBeds: [],
    medianNailAspect: 1.3,
    completeness: 1,
    duplicateCandidates: 0,
    warnings: [],
    ...overrides,
  };
}

function skin(overrides: Partial<SkinToneAnalysis> = {}): SkinToneAnalysis {
  return {
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
    ...overrides,
  };
}

function scenario(overrides: Partial<UserScenario> = {}): UserScenario {
  return { occasion: "daily", ...overrides };
}

test("黄金样例：固定输入产生确定性 top-3（id 与 ruleHits 稳定）", () => {
  const result = recommend(
    profile({ shape: "wide-short", medianNailAspect: 1.1 }),
    skin(),
    scenario({ occasion: "work" })
  );
  assert.equal(result.length, 3);
  assert.deepEqual(
    result.map((rec) => rec.id),
    ["round-short-职场裸色", "squoval-short-职场裸色", "round-short-暖调明亮色"]
  );
  assert.ok(result[0].ruleHits.includes("shape-wide-short-round"));
  assert.ok(result[0].ruleHits.includes("occasion-work-nude"));
  assert.deepEqual(result.map((rec) => rec.rank), [1, 2, 3]);
});

test("id 由 shape-length-family 确定性派生，且组合分单调不增", () => {
  const result = recommend(profile(), skin(), scenario({ occasion: "date" }));
  for (const rec of result) {
    assert.equal(rec.id, `${rec.shape}-${rec.length}-${rec.colors.family}`);
  }
  for (let index = 1; index < result.length; index += 1) {
    assert.ok(result[index].score <= result[index - 1].score + 1e-9);
  }
});

test("fallback 后端强制人工确认且置信度封顶 medium", () => {
  const result = recommend(profile(), skin(), scenario(), { backend: "fallback" });
  assert.ok(result.length > 0);
  for (const rec of result) {
    assert.equal(rec.requiresManualConfirmation, true);
    assert.notEqual(rec.confidence, "high");
  }
});

test("低置信候选同样触发人工确认", () => {
  const result = recommend(profile(), skin(), scenario(), { hasLowConfidenceCandidate: true });
  assert.equal(result[0].requiresManualConfirmation, true);
});

test("skin=null 时肤色规则失效，颜色回落到场合规则", () => {
  const result = recommend(profile(), null, scenario({ occasion: "work" }));
  assert.ok(result.length > 0);
  assert.equal(result[0].colors.family, "职场裸色");
  assert.ok(result[0].ruleHits.includes("occasion-work-nude"));
  for (const rec of result) {
    for (const hit of rec.ruleHits) {
      const rule = COLOR_RULES.find((item) => item.id === hit);
      if (rule) assert.ok(["occasion-work-nude", "occasion-daily-safe"].includes(rule.id) || !rule.id.startsWith("color-"));
    }
  }
  assert.equal(result[0].confidence, "medium");
});

test("安全硬过滤：重劳作 + 派对夸张风格时排除长甲并给出覆盖说明", () => {
  const result = recommend(
    profile(),
    skin(),
    scenario({ occasion: "party", style: "bold", manualLabor: "heavy" })
  );
  assert.ok(result.length > 0);
  for (const rec of result) {
    assert.notEqual(rec.length, "long", `不应出现长甲：${rec.id}`);
  }
  assert.ok(result[0].ruleHits.includes("safety-long-length-excluded"));
  assert.ok(result[0].explanations.some((item) => item.ruleId === "safety-long-length-excluded"));
});

test("薄软甲同样触发硬过滤与加固建议", () => {
  const result = recommend(profile(), skin(), scenario({ occasion: "party", style: "bold", nailCondition: "thin-soft" }));
  assert.ok(result.every((rec) => rec.length !== "long"));
  assert.ok(result[0].ruleHits.includes("safety-long-length-excluded"));
});

test("同一 shape+length 组合取最高权重，不重复计分", () => {
  const result = recommend(
    profile(),
    skin(),
    scenario({ occasion: "work", manualLabor: "heavy" })
  );
  const top = result[0];
  assert.equal(top.shape, "squoval");
  assert.equal(top.length, "short");
  assert.ok(top.ruleHits.includes("shape-heavy-labor-squoval"));
  assert.ok(!top.ruleHits.includes("occasion-work-squoval"), "被合并的规则不应计入 ruleHits");
  assert.ok(
    top.explanations.some((item) => item.ruleId === "occasion-work-squoval" && item.message.includes("已按更优先规则合并"))
  );
});

test("可选字段未填不得被当作否定值", () => {
  const withUndefined = recommend(
    profile({ shape: "wide-short", medianNailAspect: 1.1 }),
    skin(),
    scenario({ occasion: "daily" })
  );
  assert.ok(withUndefined.some((rec) => rec.shape === "round"), "未填 lengthPreference 不应阻止 round 规则");

  const withLong = recommend(
    profile({ shape: "wide-short", medianNailAspect: 1.1 }),
    skin(),
    scenario({ occasion: "daily", lengthPreference: "long" })
  );
  assert.ok(!withLong.some((rec) => rec.ruleHits.includes("shape-wide-short-round")));
});

test("中性底调有专属颜色规则", () => {
  const result = recommend(profile(), skin({ undertone: "neutral" }), scenario({ occasion: "daily" }));
  assert.ok(result.some((rec) => rec.colors.family === "中性平衡色"));
});

test("深肤色规则受采样质量门约束", () => {
  const lowQuality = recommend(
    profile(),
    skin({ itaBand: "dark", quality: 0.4 }),
    scenario({ occasion: "daily" })
  );
  assert.ok(!lowQuality.some((rec) => rec.ruleHits.includes("color-ita-deep-jewel")));

  const highQuality = recommend(
    profile(),
    skin({ itaBand: "dark", quality: 0.6 }),
    scenario({ occasion: "daily" })
  );
  assert.ok(highQuality.some((rec) => rec.ruleHits.includes("color-ita-deep-jewel")));
});

test("规则 id 唯一，presetNames 全部存在于 PRESET_COLORS", () => {
  const shapeIds = NAIL_SHAPE_RULES.map((rule) => rule.id);
  const colorIds = COLOR_RULES.map((rule) => rule.id);
  assert.equal(new Set(shapeIds).size, shapeIds.length);
  assert.equal(new Set(colorIds).size, colorIds.length);
  assert.equal(new Set([...shapeIds, ...colorIds]).size, shapeIds.length + colorIds.length);

  const names = new Set(PRESET_COLORS.map((item) => item.name));
  for (const rule of COLOR_RULES) {
    for (const preset of rule.colors.presetNames) {
      assert.ok(names.has(preset), `preset 不存在：${preset}`);
    }
  }
});

test("completeness 低时置信度再降一档", () => {
  const result = recommend(profile({ completeness: 0.3 }), skin(), scenario());
  assert.equal(result[0].confidence, "medium");
});

test("ITA° 分档不可靠时肤色类颜色规则全部弃权（不猜档）", () => {
  for (const reason of ["low-chroma", "near-boundary"] as const) {
    const result = recommend(
      profile(),
      skin({ itaReliable: false, itaUncertainty: reason }),
      scenario({ occasion: "daily" })
    );
    assert.ok(result.length > 0, "仍应有推荐（场合规则兜底）");
    for (const rec of result) {
      for (const hit of rec.ruleHits) {
        assert.ok(
          !hit.startsWith("color-undertone-") && !hit.startsWith("color-ita-"),
          `分档不可靠（${reason}）时不应命中肤色规则：${hit}`
        );
      }
    }
  }
});

test("分档可靠时肤色类颜色规则正常命中（弃权不会误伤正常路径）", () => {
  const result = recommend(
    profile(),
    skin({ itaReliable: true, undertone: "warm", itaBand: "light" }),
    scenario({ occasion: "daily" })
  );
  assert.ok(result.some((rec) => rec.ruleHits.includes("color-undertone-warm-bright")));
});
