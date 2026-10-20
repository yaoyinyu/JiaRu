import assert from "node:assert/strict";
import test from "node:test";

import {
  buildAnalysisBridgeParams,
  NAIL_SHAPE_WHITELIST,
  parseAnalysisBridgeParams,
} from "../src/lib/nail-personalization/bridge.ts";
import { PRESET_COLORS } from "../src/lib/utils.ts";
import type { Recommendation } from "../src/lib/nail-personalization/types.ts";

function rec(overrides: Partial<Recommendation> = {}): Recommendation {
  return {
    id: "round-short-职场裸色",
    rank: 1,
    score: 1,
    shape: "round",
    length: "short",
    colors: { family: "职场裸色", presetNames: ["裸粉色", "裸色", "奶茶色"] },
    explanations: [],
    confidence: "high",
    requiresManualConfirmation: false,
    ruleHits: [],
    ...overrides,
  };
}

test("buildAnalysisBridgeParams 输出存在于 PRESET_COLORS 的色名", () => {
  const names = new Set(PRESET_COLORS.map((item) => item.name));
  const params = buildAnalysisBridgeParams(rec());
  assert.ok(names.has(params.preset), `preset=${params.preset}`);
  assert.equal(params.shape, "round");
});

test("色号全部非法时回退到首个预设色而非抛错", () => {
  const params = buildAnalysisBridgeParams(rec({ colors: { family: "未知", presetNames: ["不存在的色号"] } }));
  assert.equal(params.preset, PRESET_COLORS[0].name);
});

test("合法参数往返解析成功", () => {
  const built = buildAnalysisBridgeParams(rec({ shape: "almond" }));
  const parsed = parseAnalysisBridgeParams(built);
  assert.equal(parsed.ok, true);
  if (parsed.ok) {
    assert.equal(parsed.preset, built.preset);
    assert.equal(parsed.shape, "almond");
  }
});

test("非法 preset / shape / 缺失字段一律拒绝", () => {
  assert.equal(parseAnalysisBridgeParams({ preset: "不存在的色号", shape: "round" }).ok, false);
  assert.equal(parseAnalysisBridgeParams({ preset: "裸粉色", shape: "triangle" }).ok, false);
  assert.equal(parseAnalysisBridgeParams({ preset: null, shape: "round" }).ok, false);
  assert.equal(parseAnalysisBridgeParams({ preset: "裸粉色", shape: null }).ok, false);
  assert.equal(parseAnalysisBridgeParams({}).ok, false);
});

test("shape 白名单覆盖全部 NailShapeAdvice", () => {
  for (const shape of NAIL_SHAPE_WHITELIST) {
    assert.equal(parseAnalysisBridgeParams({ preset: "裸粉色", shape }).ok, true);
  }
});
