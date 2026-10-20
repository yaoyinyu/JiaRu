import assert from "node:assert/strict";
import test from "node:test";

import { COLOR_RULES, NAIL_SHAPE_RULES } from "../src/lib/nail-personalization/rules.ts";
import type {
  HandProfile,
  SkinToneAnalysis,
  Undertone,
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
    itaBand: "intermediate",
    itaReliable: true,
    monkGrade: 5,
    undertone: "neutral",
    undertoneSource: "measured",
    sampleCount: 200,
    quality: 0.6,
    warnings: [],
    ...overrides,
  };
}

const SHAPE_FIXTURES: Record<string, { profile: HandProfile; scenario: UserScenario }> = {
  "shape-heavy-labor-squoval": { profile: profile(), scenario: { occasion: "daily", manualLabor: "heavy" } },
  "occasion-work-squoval": { profile: profile(), scenario: { occasion: "work" } },
  "style-low-maintenance-round": { profile: profile(), scenario: { occasion: "daily", style: "low-maintenance" } },
  "shape-wide-short-round": { profile: profile({ shape: "wide-short", medianNailAspect: 1.1 }), scenario: { occasion: "daily" } },
  "shape-narrow-long-oval": { profile: profile({ shape: "narrow-long", medianNailAspect: 1.7 }), scenario: { occasion: "daily" } },
  "shape-slim-tapered-almond": { profile: profile({ shape: "slim-tapered", medianNailAspect: 1.5, thumbRatio: 0.9 }), scenario: { occasion: "daily" } },
  "shape-balanced-squoval": { profile: profile({ shape: "balanced" }), scenario: { occasion: "daily" } },
  "occasion-wedding-oval": { profile: profile(), scenario: { occasion: "wedding" } },
  "occasion-party-bold-almond": { profile: profile(), scenario: { occasion: "party", style: "bold" } },
  "shape-short-bed-round": { profile: profile({ medianNailAspect: 1.1 }), scenario: { occasion: "daily" } },
  "nail-condition-thin-soft": { profile: profile(), scenario: { occasion: "daily", nailCondition: "thin-soft" } },
};

const COLOR_FIXTURES: Record<string, { skin: SkinToneAnalysis | null; scenario: UserScenario }> = {
  "occasion-work-nude": { skin: skin(), scenario: { occasion: "work" } },
  "occasion-wedding-elegant": { skin: skin(), scenario: { occasion: "wedding" } },
  "color-undertone-warm-rich": { skin: skin({ undertone: "warm", itaBand: "brown" }), scenario: { occasion: "daily" } },
  "color-undertone-cool-soft": { skin: skin({ undertone: "cool" }), scenario: { occasion: "daily" } },
  "color-undertone-warm-bright": { skin: skin({ undertone: "warm", itaBand: "light" }), scenario: { occasion: "daily" } },
  "color-undertone-neutral-balanced": { skin: skin({ undertone: "neutral" }), scenario: { occasion: "daily" } },
  "color-ita-deep-jewel": { skin: skin({ itaBand: "dark", quality: 0.6 }), scenario: { occasion: "daily" } },
  "occasion-party-bold": { skin: skin(), scenario: { occasion: "party", style: "bold" } },
  "color-undertone-olive-earth": { skin: skin({ undertone: "olive" }), scenario: { occasion: "daily" } },
  "color-ita-fair-soft": { skin: skin({ itaBand: "light", undertone: "cool" }), scenario: { occasion: "daily" } },
  "occasion-date-romantic": { skin: skin(), scenario: { occasion: "date" } },
  "occasion-vacation-bright": { skin: skin(), scenario: { occasion: "vacation" } },
  "occasion-daily-safe": { skin: skin(), scenario: { occasion: "daily" } },
  "length-optical-light": { skin: skin(), scenario: { occasion: "work", lengthPreference: "short" } },
  "nail-condition-safe-base": { skin: skin(), scenario: { occasion: "daily", nailCondition: "brittle" } },
};

test("每条甲型规则都有命中 fixture（防「有规则无测试」）", () => {
  for (const rule of NAIL_SHAPE_RULES) {
    const fixture = SHAPE_FIXTURES[rule.id];
    assert.ok(fixture, `甲型规则 ${rule.id} 缺少 fixture`);
    assert.equal(
      rule.when(fixture.profile, fixture.scenario),
      true,
      `甲型规则 ${rule.id} 在其 fixture 上未命中`
    );
    assert.ok(rule.explain(fixture.profile, fixture.scenario).length > 0, `${rule.id} 文案为空`);
    assert.ok(rule.weight > 0, `${rule.id} 权重非正`);
  }
});

test("每条颜色规则都有命中 fixture（防「有规则无测试」）", () => {
  for (const rule of COLOR_RULES) {
    const fixture = COLOR_FIXTURES[rule.id];
    assert.ok(fixture, `颜色规则 ${rule.id} 缺少 fixture`);
    assert.equal(
      rule.when(fixture.skin, fixture.scenario),
      true,
      `颜色规则 ${rule.id} 在其 fixture 上未命中`
    );
    assert.ok(rule.explain(fixture.skin, fixture.scenario).length > 0, `${rule.id} 文案为空`);
    assert.ok(rule.weight > 0, `${rule.id} 权重非正`);
    assert.ok(rule.colors.presetNames.length > 0, `${rule.id} 无色号`);
  }
});

test("fixture 清单与规则表一一对应，无多余或遗漏", () => {
  assert.deepEqual(
    Object.keys(SHAPE_FIXTURES).sort(),
    NAIL_SHAPE_RULES.map((rule) => rule.id).sort()
  );
  assert.deepEqual(
    Object.keys(COLOR_FIXTURES).sort(),
    COLOR_RULES.map((rule) => rule.id).sort()
  );
});

test("底调四值各有专属颜色规则", () => {
  const undertones: Undertone[] = ["warm", "cool", "neutral", "olive"];
  for (const undertone of undertones) {
    // warm 规则按 ITA 档位分叉，统一取 light 档以命中暖调明亮色规则。
    const matched = COLOR_RULES.filter(
      (rule) =>
        rule.id.startsWith("color-undertone-")
        && rule.when(skin({ undertone, itaBand: "light" }), { occasion: "daily" })
    );
    assert.ok(matched.length > 0, `底调 ${undertone} 无专属规则`);
  }
});
