import type { ItaBand, MonkGrade, Undertone } from "./types.ts";

/**
 * ITA° 分档边界（左开右闭）：
 * ita > 55 → very-light；41 < ita ≤ 55 → light；28 < ita ≤ 41 → intermediate；
 * 10 < ita ≤ 28 → tan；-30 < ita ≤ 10 → brown；ita ≤ -30 → dark。
 * 依据 [S80]（ITA° 原始定义，经 [S38][S39] 转引）与 [S38]（同行评审）。
 * 均为预注册假设，标定要求见设计文档 §8。
 */
export const ITA_BAND_BOUNDS = [55, 41, 28, 10, -30] as const;

/** 底调判定常量。b* 居中区间量化为 [4, 14] 闭区间。 */
export const UNDERTONE_WARM_B = 14;
export const UNDERTONE_COOL_B_LOW = 4;
export const UNDERTONE_OLIVE_A = 2;

/**
 * ITA° → Monk 十级映射边界（降序）。索引 +1 即 Monk 等级，全部落空则为 10。
 * 口径来源 [S38]（ITA° → Monk 映射），与 L* 线性近似无关；
 * Monk 标度为十级开源肤色标度 [S40]，本映射仅供色号筛选沟通，不是标准 Monk 评估。
 */
export const MONK_ITA_BOUNDS = [55, 45, 35, 25, 15, 5, -5, -15, -30] as const;

const D65_WHITE = { x: 0.95047, y: 1, z: 1.08883 };
const EPSILON = 216 / 24389; // 0.008856
const KAPPA = 24389 / 27; // 903.3

export interface Lab {
  L: number;
  a: number;
  b: number;
}

function srgbToLinear(channel: number): number {
  const normalized = clamp01(channel / 255) ;
  return normalized <= 0.04045 ? normalized / 12.92 : Math.pow((normalized + 0.055) / 1.055, 2.4);
}

function clamp01(value: number): number {
  return Math.max(0, Math.min(1, value));
}

function pivot(value: number): number {
  return value > EPSILON ? Math.cbrt(value) : (KAPPA * value + 16) / 116;
}

/** sRGB（0–255）→ CIELAB（D65）。输入越界时按 0–255 截断，不抛错。 */
export function rgbToLab(r: number, g: number, b: number): Lab {
  const lr = srgbToLinear(r);
  const lg = srgbToLinear(g);
  const lb = srgbToLinear(b);

  const x = (0.4124564 * lr + 0.3575761 * lg + 0.1804375 * lb) / D65_WHITE.x;
  const y = (0.2126729 * lr + 0.7151522 * lg + 0.072175 * lb) / D65_WHITE.y;
  const z = (0.0193339 * lr + 0.119192 * lg + 0.9503041 * lb) / D65_WHITE.z;

  const fx = pivot(x);
  const fy = pivot(y);
  const fz = pivot(z);

  return {
    L: 116 * fy - 16,
    a: 500 * (fx - fy),
    b: 200 * (fy - fz),
  };
}

/**
 * ITA° = arctan((L* − 50) / b*) × 180 / π。
 * b* 为 0 时按极限处理：L* > 50 → 90；L* < 50 → −90；L* = 50 → 0。
 */
export function individualTypologyAngle(lab: Lab): number {
  const numerator = lab.L - 50;
  if (lab.b === 0) {
    if (numerator > 0) return 90;
    if (numerator < 0) return -90;
    return 0;
  }
  return (Math.atan(numerator / lab.b) * 180) / Math.PI;
}

/** 左开右闭分档，逐值与 ITA_BAND_BOUNDS 对齐。 */
export function classifyItaBand(ita: number): ItaBand {
  if (ita > ITA_BAND_BOUNDS[0]) return "very-light";
  if (ita > ITA_BAND_BOUNDS[1]) return "light";
  if (ita > ITA_BAND_BOUNDS[2]) return "intermediate";
  if (ita > ITA_BAND_BOUNDS[3]) return "tan";
  if (ita > ITA_BAND_BOUNDS[4]) return "brown";
  return "dark";
}

/**
 * ITA° → Monk 十级近似。仅供色号筛选沟通，不是标准 Monk 评估；
 * 项目不输出 Fitzpatrick（资料汇编 §2.5 第 2 条：Fitzpatrick 存在偏向浅肤色的系统偏见）。
 */
export function approximateMonkGrade(lab: Lab): MonkGrade {
  const ita = individualTypologyAngle(lab);
  for (let index = 0; index < MONK_ITA_BOUNDS.length; index += 1) {
    if (ita > MONK_ITA_BOUNDS[index]) return (index + 1) as MonkGrade;
  }
  return 10;
}

/**
 * 底调判定，按序命中即返回：
 * ① 橄榄：a* > 2 且 b* ≥ 4（橄榄优先于暖，故 `a* > 2 且 b* > 14` 也判橄榄，消除优先级空洞）；
 * ② 暖：b* > 14；③ 冷：b* < 4 且 a* < 0；④ 其余中性。
 */
export function classifyUndertone(lab: Lab): Undertone {
  const { a, b } = lab;
  if (a > UNDERTONE_OLIVE_A && b >= UNDERTONE_COOL_B_LOW) return "olive";
  if (b > UNDERTONE_WARM_B) return "warm";
  if (b < UNDERTONE_COOL_B_LOW && a < 0) return "cool";
  return "neutral";
}

/** ΔE76（CIE 1976）色差。 */
export function labDistance(a: Lab, b: Lab): number {
  const dL = a.L - b.L;
  const da = a.a - b.a;
  const db = a.b - b.b;
  return Math.sqrt(dL * dL + da * da + db * db);
}

/**
 * |b*| 小于该值时，ITA° 的分母接近 0，atan((L*−50)/b*) 饱和到 ±90，
 * 分档完全由 b* 的符号决定而与肤色深浅无关（b*=−0.25 与 +0.25 会分别落到
 * dark 与 very-light 两个极端档）。取与 UNDERTONE_COOL_B_LOW 同源的 4，
 * 属预注册假设，标定要求见设计文档 §8。
 */
export const ITA_UNSTABLE_B_ABS = 4;

/** 距任一分档边界小于该角度时，认为分档对照射波动敏感，band 相关规则弃权。 */
export const ITA_BOUNDARY_MARGIN = 3;

export type ItaUncertaintyReason = "low-chroma" | "near-boundary";

export interface ItaClassification {
  band: ItaBand;
  /** false 表示分档不可靠，消费该分档的规则必须弃权，不得当作硬事实使用。 */
  reliable: boolean;
  reason?: ItaUncertaintyReason;
}

/**
 * 带可靠性判定的 ITA° 分档。
 *
 * 为什么需要它：ITA° 原始定义 [S80] 建立在受控测量条件下，直接用于非受控
 * 拍照时有两个已实证的失效模式——①|b*| 接近 0 时分档由 b* 符号决定（数值缺陷）；
 * ②距分档边界数度时，20–30% 的照度变化或光源色温变化即可跨档。
 * 两者都通过 `reliable=false` 让调用方弃权，而不是给一个看似精确的错档。
 */
export function classifyItaBandStable(lab: Lab): ItaClassification {
  const ita = individualTypologyAngle(lab);
  const band = classifyItaBand(ita);
  if (Math.abs(lab.b) < ITA_UNSTABLE_B_ABS) {
    return { band, reliable: false, reason: "low-chroma" };
  }
  if (ITA_BAND_BOUNDS.some((bound) => Math.abs(ita - bound) < ITA_BOUNDARY_MARGIN)) {
    return { band, reliable: false, reason: "near-boundary" };
  }
  return { band, reliable: true };
}
