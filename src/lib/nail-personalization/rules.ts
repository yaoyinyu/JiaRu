import type {
  ColorAdvice,
  HandProfile,
  LengthAdvice,
  NailShapeAdvice,
  Recommendation,
  RecommendationExplanation,
  SkinToneAnalysis,
  UserScenario,
} from "./types.ts";
import { isKnown } from "./types.ts";

/** 组合分权重（归一化后加权，和为 1）。 */
export const SHAPE_COLOR_BLEND = { shape: 0.5, color: 0.5 } as const;

/** 触发安全硬过滤的条件：重劳作或薄软/易断甲不得推荐长甲。 */
export const LONG_LENGTH_EXCLUDED_RULE_ID = "safety-long-length-excluded";

export interface NailShapeRule {
  id: string;
  weight: number;
  shape: NailShapeAdvice;
  length: LengthAdvice;
  when: (profile: HandProfile, scenario: UserScenario) => boolean;
  explain: (profile: HandProfile, scenario: UserScenario) => string;
}

export interface ColorRule {
  id: string;
  weight: number;
  colors: ColorAdvice;
  when: (skin: SkinToneAnalysis | null, scenario: UserScenario) => boolean;
  explain: (skin: SkinToneAnalysis | null, scenario: UserScenario) => string;
}

/** 未知长度偏好不得当作"非长"：未填视为不阻止该规则。 */
function lengthPreferenceAllows(scenario: UserScenario, blocked: LengthAdvice): boolean {
  return !isKnown(scenario.lengthPreference) || scenario.lengthPreference !== blocked;
}

/**
 * 肤色测量（ITA° 分档与底调）是否可用。
 * `itaReliable === false` 表示 |b*| 接近 0（ITA° 分母趋零、分档由 b* 符号决定）
 * 或距分档边界过近（照度/色温小变化即跨档），此时**消费该测量的颜色规则一律弃权**，
 * 改由场合/风格/甲面状况规则兜底，而不是给出一个看似精确的错档推荐。
 */
function chromaUsable(skin: SkinToneAnalysis | null): skin is SkinToneAnalysis {
  return skin !== null && skin.itaReliable === true;
}

const NAIL_SHAPE_ADVICE_LABEL: Record<NailShapeAdvice, string> = {
  round: "圆形",
  squoval: "方圆形",
  square: "方形",
  oval: "椭圆形",
  almond: "杏仁形",
  coffin: "棺形",
  stiletto: "尖形",
};

const LENGTH_ADVICE_LABEL: Record<LengthAdvice, string> = {
  short: "短甲",
  medium: "中长甲",
  long: "长甲",
};

export const NAIL_SHAPE_RULES: readonly NailShapeRule[] = [
  {
    id: "shape-heavy-labor-squoval",
    weight: 4,
    shape: "squoval",
    length: "short",
    when: (_profile, scenario) => scenario.manualLabor === "heavy",
    explain: () => "你常做重体力或手工作业，方圆形短甲边角厚、不易劈裂，洗漱与日常更耐用。",
  },
  {
    id: "occasion-work-squoval",
    weight: 3,
    shape: "squoval",
    length: "short",
    when: (_profile, scenario) => scenario.occasion === "work",
    explain: () => "职场通勤需要低调不打扰，短方圆形稳重，不耽误键盘与日常操作。",
  },
  {
    id: "style-low-maintenance-round",
    weight: 3,
    shape: "round",
    length: "short",
    when: (_profile, scenario) => scenario.style === "low-maintenance",
    explain: () => "你偏好低维护，圆形甲长出后最自然，不需要频繁修型。",
  },
  {
    id: "shape-wide-short-round",
    weight: 3,
    shape: "round",
    length: "short",
    when: (profile, scenario) =>
      profile.shape === "wide-short" && lengthPreferenceAllows(scenario, "long"),
    explain: (profile) =>
      `测得甲床偏短宽（长宽比中位数 ${profile.medianNailAspect.toFixed(2)}），圆形收敛两侧更显修长。`,
  },
  {
    id: "shape-narrow-long-oval",
    weight: 3,
    shape: "oval",
    length: "medium",
    when: (profile, scenario) =>
      profile.shape === "narrow-long" && scenario.occasion !== "party",
    explain: (profile) =>
      `测得甲床偏长窄（长宽比中位数 ${profile.medianNailAspect.toFixed(2)}），椭圆形顺应自然比例。`,
  },
  {
    id: "shape-slim-tapered-almond",
    weight: 2,
    shape: "almond",
    length: "medium",
    when: (profile) => profile.shape === "slim-tapered",
    explain: () => "拇指相对窄且甲面偏长，杏仁形可以延伸出更优雅的线条。",
  },
  {
    id: "shape-balanced-squoval",
    weight: 2,
    shape: "squoval",
    length: "medium",
    when: (profile) => profile.shape === "balanced",
    explain: () => "手型比例均衡，方圆形百搭且耐用，中长长度好打理。",
  },
  {
    id: "occasion-wedding-oval",
    weight: 2,
    shape: "oval",
    length: "medium",
    when: (_profile, scenario) =>
      scenario.occasion === "wedding" && lengthPreferenceAllows(scenario, "short"),
    explain: () => "婚礼场合中长椭圆或杏仁形，能衬婚纱与戒指而不抢焦点。",
  },
  {
    id: "occasion-party-bold-almond",
    weight: 2,
    shape: "almond",
    length: "long",
    when: (_profile, scenario) => scenario.occasion === "party" && scenario.style === "bold",
    explain: () => "派对加上夸张风格，杏仁长甲更有存在感；长度仍以你日常能承受为准。",
  },
  {
    id: "shape-short-bed-round",
    weight: 2,
    shape: "round",
    length: "short",
    when: (profile) => profile.medianNailAspect < 1.2 && profile.shape !== "wide-short",
    explain: (profile) =>
      `甲床偏短（长宽比中位数 ${profile.medianNailAspect.toFixed(2)}），圆形不需要额外长度基底。`,
  },
  {
    id: "nail-condition-thin-soft",
    weight: 3,
    shape: "squoval",
    length: "short",
    when: (_profile, scenario) =>
      scenario.nailCondition === "thin-soft" || scenario.nailCondition === "brittle",
    explain: () => "甲面薄软或易断，建议先用建构胶或水晶甲加固，再谈款式与长度。",
  },
];

export const COLOR_RULES: readonly ColorRule[] = [
  {
    id: "occasion-work-nude",
    weight: 4,
    colors: { family: "职场裸色", presetNames: ["裸粉色", "裸色", "奶茶色"] },
    when: (_skin, scenario) => scenario.occasion === "work",
    explain: () => "职场通勤选裸色系最稳，干净且不抢眼。",
  },
  {
    id: "occasion-wedding-elegant",
    weight: 4,
    colors: { family: "婚礼优雅色", presetNames: ["裸粉色", "纯白色", "银色"] },
    when: (_skin, scenario) => scenario.occasion === "wedding",
    explain: () => "婚礼场合以优雅裸粉、法式白边与细闪最稳妥，不抢婚纱与婚戒。",
  },
  {
    id: "color-undertone-warm-rich",
    weight: 3,
    colors: { family: "暖调浓郁色", presetNames: ["酒红色", "焦糖色", "樱桃红"], season: "autumn" },
    when: (skin) => chromaUsable(skin) && skin.undertone === "warm" && (skin.itaBand === "brown" || skin.itaBand === "tan"),
    explain: (skin) =>
      `测得偏暖底调${skin ? `（b* ${skin.lab.b.toFixed(1)}）` : ""}，且肤色偏深，浓郁暖色更提气色。`,
  },
  {
    id: "color-undertone-cool-soft",
    weight: 3,
    colors: { family: "冷调柔雾色", presetNames: ["雾霾蓝", "薰衣草紫", "豆沙红"], season: "summer" },
    when: (skin) => chromaUsable(skin) && skin.undertone === "cool",
    explain: (skin) => `测得偏冷底调${skin ? `（b* ${skin.lab.b.toFixed(1)}）` : ""}，柔雾冷色更协调。`,
  },
  {
    id: "color-undertone-warm-bright",
    weight: 3,
    colors: { family: "暖调明亮色", presetNames: ["珊瑚粉", "橘色", "金色"], season: "spring" },
    when: (skin) =>
      chromaUsable(skin) && skin.undertone === "warm" && (skin.itaBand === "very-light" || skin.itaBand === "light"),
    explain: () => "测得偏暖底调且肤色偏浅，明亮的珊瑚、橘与金色更有活力。",
  },
  {
    id: "color-undertone-neutral-balanced",
    weight: 3,
    colors: { family: "中性平衡色", presetNames: ["酒红色", "豆沙红", "裸粉色"] },
    when: (skin) => chromaUsable(skin) && skin.undertone === "neutral",
    explain: () => "测得中性底调，冷暖跨度都能驾驭，正红系与平衡裸粉最稳。",
  },
  {
    id: "color-ita-deep-jewel",
    weight: 3,
    colors: { family: "宝石亮色", presetNames: ["玫红色", "深蓝色", "金色"], season: "winter" },
    when: (skin) => chromaUsable(skin) && skin.itaBand === "dark" && skin.quality >= 0.5,
    explain: () => "测得较深肤色（采样质量达标），宝石亮色与金属色对比鲜明、更显精致。",
  },
  {
    id: "occasion-party-bold",
    weight: 3,
    colors: { family: "派对闪耀色", presetNames: ["亮片银", "金色", "黑色"] },
    when: (_skin, scenario) => scenario.occasion === "party" && scenario.style === "bold",
    explain: () => "派对加夸张风格，亮片与金属色最出片。",
  },
  {
    id: "color-undertone-olive-earth",
    weight: 2,
    colors: { family: "大地浓郁色", presetNames: ["焦糖色", "抹茶绿", "奶茶色"], season: "autumn" },
    when: (skin) => chromaUsable(skin) && skin.undertone === "olive",
    explain: () => "测得橄榄底调，大地色系比惨白 pastel 更显质感。",
  },
  {
    id: "color-ita-fair-soft",
    weight: 2,
    colors: { family: "柔粉淡紫", presetNames: ["裸粉色", "豆沙红", "薰衣草紫"], season: "summer" },
    when: (skin) =>
      chromaUsable(skin)
      && (skin.itaBand === "very-light" || skin.itaBand === "light")
      && skin.undertone !== "warm",
    explain: () => "测得偏浅肤色且非暖调，柔粉与淡紫更干净。",
  },
  {
    id: "occasion-date-romantic",
    weight: 2,
    colors: { family: "约会浪漫色", presetNames: ["酒红色", "豆沙红", "樱桃红"] },
    when: (_skin, scenario) => scenario.occasion === "date",
    explain: () => "约会场合选浪漫红调与深浆果色，温柔又有记忆点。",
  },
  {
    id: "occasion-vacation-bright",
    weight: 2,
    colors: { family: "度假明亮色", presetNames: ["珊瑚粉", "橘色", "抹茶绿"] },
    when: (_skin, scenario) => scenario.occasion === "vacation",
    explain: () => "度假场合用明亮珊瑚与热带色调，上镜更轻快。",
  },
  {
    id: "occasion-daily-safe",
    weight: 1,
    colors: { family: "日常安全色", presetNames: ["裸粉色", "豆沙红", "珊瑚粉"] },
    when: (_skin, scenario) => scenario.occasion === "daily",
    explain: () => "日常通勤与家务兼顾，安全裸粉与豆沙最不容易出错。",
  },
  {
    id: "length-optical-light",
    weight: 1,
    colors: { family: "浅裸拉长色", presetNames: ["裸粉色", "裸色", "纯白色"] },
    when: (_skin, scenario) => scenario.lengthPreference === "short",
    explain: () => "偏好短甲时，浅裸色在视觉上更能拉长手指。",
  },
  {
    id: "nail-condition-safe-base",
    weight: 1,
    colors: { family: "加固友好色", presetNames: ["裸粉色", "奶茶色", "裸色"] },
    when: (_skin, scenario) =>
      scenario.nailCondition === "thin-soft" || scenario.nailCondition === "brittle",
    explain: () => "甲面薄软时先用浅色，便于观察甲面变化，配合加固护理。",
  },
];

/** 无任何颜色规则命中时的兜底，保证推荐始终带色系。 */
export const FALLBACK_COLOR_ADVICE: ColorAdvice = {
  family: "日常安全色",
  presetNames: ["裸粉色", "豆沙红", "珊瑚粉"],
};

interface CombinationScore<T> {
  key: string;
  weight: number;
  hits: T[];
}

function aggregateShapeHits(
  profile: HandProfile,
  scenario: UserScenario
): Map<string, CombinationScore<NailShapeRule>> {
  const map = new Map<string, CombinationScore<NailShapeRule>>();
  for (const rule of NAIL_SHAPE_RULES) {
    if (!rule.when(profile, scenario)) continue;
    const key = `${rule.shape}/${rule.length}`;
    const existing = map.get(key);
    if (!existing) {
      map.set(key, { key, weight: rule.weight, hits: [rule] });
      continue;
    }
    // 同组合不重复计分：取最高权重，其余合并为 info 说明。
    if (rule.weight > existing.weight) {
      map.set(key, { key, weight: rule.weight, hits: [rule, ...existing.hits] });
    } else {
      existing.hits.push(rule);
    }
  }
  return map;
}

function aggregateColorHits(
  skin: SkinToneAnalysis | null,
  scenario: UserScenario
): Map<string, CombinationScore<ColorRule>> {
  const map = new Map<string, CombinationScore<ColorRule>>();
  for (const rule of COLOR_RULES) {
    if (!rule.when(skin, scenario)) continue;
    const key = rule.colors.family;
    const existing = map.get(key);
    if (!existing) {
      map.set(key, { key, weight: rule.weight, hits: [rule] });
      continue;
    }
    if (rule.weight > existing.weight) {
      map.set(key, { key, weight: rule.weight, hits: [rule, ...existing.hits] });
    } else {
      existing.hits.push(rule);
    }
  }
  return map;
}

function requiresSafetyFilter(scenario: UserScenario): boolean {
  return scenario.manualLabor === "heavy"
    || scenario.nailCondition === "thin-soft"
    || scenario.nailCondition === "brittle";
}

function downgrade(confidence: "high" | "medium" | "low"): "high" | "medium" | "low" {
  return confidence === "high" ? "medium" : "low";
}

export function recommend(
  profile: HandProfile,
  skin: SkinToneAnalysis | null,
  scenario: UserScenario,
  options?: {
    backend?: "model" | "fallback";
    topK?: number;
    hasLowConfidenceCandidate?: boolean;
  }
): Recommendation[] {
  const topK = Math.max(1, options?.topK ?? 3);

  let shapeMap = aggregateShapeHits(profile, scenario);
  const safetyFiltered = requiresSafetyFilter(scenario);
  if (safetyFiltered) {
    const filtered = new Map<string, CombinationScore<NailShapeRule>>();
    for (const [key, value] of shapeMap) {
      if (key.endsWith("/long")) continue;
      filtered.set(key, value);
    }
    if (filtered.size > 0) shapeMap = filtered;
  }

  const colorMap = aggregateColorHits(skin, scenario);

  const shapeEntries = [...shapeMap.values()].sort(
    (left, right) => right.weight - left.weight || left.key.localeCompare(right.key)
  );
  const colorEntries = [...colorMap.values()].sort(
    (left, right) => right.weight - left.weight || left.key.localeCompare(right.key)
  );

  const shapeTop = shapeEntries.slice(0, 3);
  const colorTop = colorEntries.slice(0, 3);
  const maxShapeWeight = shapeTop.length > 0 ? shapeTop[0].weight : 1;
  const maxColorWeight = colorTop.length > 0 ? colorTop[0].weight : 1;

  const fallbackColor: CombinationScore<ColorRule> = {
    key: FALLBACK_COLOR_ADVICE.family,
    weight: 0,
    hits: [],
  };
  const usableColors = colorTop.length > 0 ? colorTop : [fallbackColor];

  const combinations: Array<{
    shape: CombinationScore<NailShapeRule>;
    color: CombinationScore<ColorRule>;
    score: number;
  }> = [];
  for (const shape of shapeTop) {
    for (const color of usableColors) {
      const shapeNorm = shape.weight / maxShapeWeight;
      const colorNorm = color.weight / maxColorWeight;
      combinations.push({
        shape,
        color,
        score: SHAPE_COLOR_BLEND.shape * shapeNorm + SHAPE_COLOR_BLEND.color * colorNorm,
      });
    }
  }

  combinations.sort(
    (left, right) =>
      right.score - left.score
      || right.shape.weight - left.shape.weight
      || left.shape.key.localeCompare(right.shape.key)
      || left.color.key.localeCompare(right.color.key)
  );

  const safetyHit = safetyFiltered
    && NAIL_SHAPE_RULES.some((rule) => rule.length === "long" && rule.when(profile, scenario));

  let confidence: "high" | "medium" | "low" = "high";
  let requiresManualConfirmation = false;
  if (options?.backend === "fallback" || options?.hasLowConfidenceCandidate) {
    confidence = "medium";
    requiresManualConfirmation = true;
  }
  if (profile.completeness < 0.6 || skin === null) confidence = downgrade(confidence);
  if (requiresManualConfirmation && confidence === "high") confidence = "medium";

  const recommendations: Recommendation[] = [];
  const seen = new Set<string>();

  for (const combination of combinations) {
    if (recommendations.length >= topK) break;
    const primary = combination.shape.hits[0];
    if (!primary) continue;
    const shape = primary.shape;
    const length = primary.length;
    const family = combination.color.hits[0]?.colors.family ?? FALLBACK_COLOR_ADVICE.family;
    const presetNames = combination.color.hits[0]?.colors.presetNames ?? FALLBACK_COLOR_ADVICE.presetNames;
    const season = combination.color.hits[0]?.colors.season;
    const id = `${shape}-${length}-${family}`;
    if (seen.has(id)) continue;
    seen.add(id);

    const explanations: RecommendationExplanation[] = [];
    if (safetyHit) {
      explanations.push({
        ruleId: LONG_LENGTH_EXCLUDED_RULE_ID,
        message: "重劳作或甲面薄软时已排除长甲方案，优先保证耐用与甲面健康。",
        severity: "warning",
      });
    }
    explanations.push({
      ruleId: primary.id,
      message: primary.explain(profile, scenario),
      severity: primary.weight >= 4 ? "warning" : "info",
    });
    for (const merged of combination.shape.hits.slice(1)) {
      explanations.push({
        ruleId: merged.id,
        message: `${merged.explain(profile, scenario)}（已按更优先规则合并，不重复计分）`,
        severity: "info",
      });
    }
    const colorPrimary = combination.color.hits[0];
    if (colorPrimary) {
      explanations.push({
        ruleId: colorPrimary.id,
        message: colorPrimary.explain(skin, scenario),
        severity: colorPrimary.weight >= 4 ? "warning" : "info",
      });
      for (const merged of combination.color.hits.slice(1)) {
        explanations.push({
          ruleId: merged.id,
          message: `${merged.explain(skin, scenario)}（已按更优先规则合并，不重复计分）`,
          severity: "info",
        });
      }
    } else {
      explanations.push({
        ruleId: "color_fallback_default",
        message: "未能取得可靠肤色采样，颜色建议改用日常安全色兜底。",
        severity: "info",
      });
    }

    recommendations.push({
      id,
      rank: recommendations.length + 1,
      score: Number(combination.score.toFixed(6)),
      shape,
      length,
      colors: { family, presetNames, ...(season ? { season } : {}) },
      explanations,
      confidence,
      requiresManualConfirmation,
      ruleHits: [
        ...(safetyHit ? [LONG_LENGTH_EXCLUDED_RULE_ID] : []),
        primary.id,
        ...(colorPrimary ? [colorPrimary.id] : []),
      ],
    });
  }

  return recommendations;
}

export function describeShape(shape: NailShapeAdvice): string {
  return NAIL_SHAPE_ADVICE_LABEL[shape];
}

export function describeLength(length: LengthAdvice): string {
  return LENGTH_ADVICE_LABEL[length];
}
