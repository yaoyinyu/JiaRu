import assert from "node:assert/strict";
import test from "node:test";

import {
  classifyItaBand,
  classifyItaBandStable,
  classifyUndertone,
  individualTypologyAngle,
  ITA_BOUNDARY_MARGIN,
  ITA_UNSTABLE_B_ABS,
  rgbToLab,
} from "../src/lib/nail-personalization/color-science.ts";
import {
  MIN_SKIN_SAMPLES,
  SKIN_QUALITY_MIN,
} from "../src/lib/nail-personalization/skin-sampling.ts";
import type { ItaBand, Undertone } from "../src/lib/nail-personalization/types.ts";

const ALL_BANDS: readonly ItaBand[] = [
  "very-light",
  "light",
  "intermediate",
  "tan",
  "brown",
  "dark",
];
const ALL_UNDERTONES: readonly Undertone[] = ["warm", "cool", "neutral", "olive"];

test("ITA° 六档在 L* 扫描中全部可达", () => {
  const seen = new Set<ItaBand>();
  for (let l = 10; l <= 100; l += 1) {
    seen.add(classifyItaBand(individualTypologyAngle({ L: l, a: 0, b: 12 })));
  }
  for (const band of ALL_BANDS) {
    assert.ok(seen.has(band), `band ${band} 未覆盖`);
  }
});

test("底调四类在 (a*, b*) 扫描中全部可达", () => {
  const seen = new Set<Undertone>();
  for (let a = -10; a <= 10; a += 1) {
    for (let b = -5; b <= 30; b += 1) {
      seen.add(classifyUndertone({ L: 60, a, b }));
    }
  }
  for (const undertone of ALL_UNDERTONES) {
    assert.ok(seen.has(undertone), `undertone ${undertone} 未覆盖`);
  }
});

test("同色温下照度衰减使 ITA° 单调下降（系统性偏差方向可复现）", () => {
  const base: [number, number, number] = [220, 180, 160];
  // 前置条件：该 fixture 的 b* 必须远离 0，否则 ITA° 由 b* 符号主导、单调性不成立
  // （浅中性皮肤在 b*≈0 时会出现 +89 → −89 的非单调翻转，见下一组断言）。
  for (const factor of [1, 0.8, 0.6, 0.45]) {
    const lab = rgbToLab(base[0] * factor, base[1] * factor, base[2] * factor);
    assert.ok(
      Math.abs(lab.b) >= ITA_UNSTABLE_B_ABS,
      `fixture b*=${lab.b.toFixed(2)} 过于接近 0，单调性断言不适用`
    );
  }
  const angles = [1, 0.8, 0.6, 0.45].map((factor) => {
    const lab = rgbToLab(base[0] * factor, base[1] * factor, base[2] * factor);
    return individualTypologyAngle(lab);
  });
  for (let index = 1; index < angles.length; index += 1) {
    assert.ok(
      angles[index] < angles[index - 1],
      `第 ${index} 级衰减 ITA°=${angles[index].toFixed(2)} 未低于上一级 ${angles[index - 1].toFixed(2)}`
    );
  }
});

test("阴影会把浅肤色压到更低 ITA° 档位（质量门存在的必要性证据）", () => {
  const bright = rgbToLab(220, 180, 160);
  const shadowed = rgbToLab(220 * 0.45, 180 * 0.45, 160 * 0.45);
  const brightBand = classifyItaBand(individualTypologyAngle(bright));
  const shadowBand = classifyItaBand(individualTypologyAngle(shadowed));
  assert.equal(brightBand, "very-light");
  assert.notEqual(shadowBand, brightBand);
  assert.ok(["brown", "dark"].includes(shadowBand), `shadowBand=${shadowBand}`);
});

test("深肤色误判缓解手段：采样质量门与采样数下限常量就位", () => {
  assert.equal(SKIN_QUALITY_MIN, 0.35);
  assert.equal(MIN_SKIN_SAMPLES, 120);
  assert.ok(MIN_SKIN_SAMPLES > 0 && SKIN_QUALITY_MIN > 0 && SKIN_QUALITY_MIN < 1);
});

test("b* 接近 0 时 ITA° 由 b* 符号主导，分档在最浅与最深之间翻转（数值缺陷回归）", () => {
  const negative = individualTypologyAngle({ L: 70, a: 0, b: -0.25 });
  const positive = individualTypologyAngle({ L: 70, a: 0, b: 0.25 });
  assert.ok(negative < -80, `b*=-0.25 应落到 −80 以下，实际 ${negative}`);
  assert.ok(positive > 80, `b*=+0.25 应落到 +80 以上，实际 ${positive}`);
  assert.equal(classifyItaBand(negative), "dark");
  assert.equal(classifyItaBand(positive), "very-light");
});

test("|b*| 小于阈值时分档判为不可靠，消费它的规则必须弃权", () => {
  for (const b of [-3.9, -1, -0.25, 0, 0.25, 1, 3.9]) {
    const result = classifyItaBandStable({ L: 70, a: 0, b });
    assert.equal(result.reliable, false, `b*=${b} 应判不可靠`);
    assert.equal(result.reason, "low-chroma");
  }
  // 阈值之外必须恢复可靠，避免弃权误伤正常彩度皮肤。
  for (const b of [-8, -4.5, 4.5, 12, 20]) {
    const result = classifyItaBandStable({ L: 70, a: 0, b });
    assert.equal(result.reliable, true, `b*=${b} 应判可靠`);
  }
});

test("距分档边界过近时判为不可靠（照度/色温小变化即跨档）", () => {
  // 固定 b*=20 以远离 low-chroma 分支，单独考察边界余量。
  // 由 ITA° = atan((L−50)/b*)×180/π 反解 L，构造出精确逼近边界的样本。
  const labAtIta = (targetIta: number) => {
    const b = 20;
    const l = 50 + b * Math.tan((targetIta * Math.PI) / 180);
    return { L: l, a: 0, b };
  };
  for (const targetIta of [53, 54.5, 55, 55.5, 57]) {
    const result = classifyItaBandStable(labAtIta(targetIta));
    assert.equal(result.reliable, false, `ITA=${targetIta} 距 55 边界过近，应判不可靠`);
    assert.equal(result.reason, "near-boundary");
  }
  for (const targetIta of [45, 48, 62, 70]) {
    assert.equal(
      classifyItaBandStable(labAtIta(targetIta)).reliable,
      true,
      `ITA=${targetIta} 距边界超过 ${ITA_BOUNDARY_MARGIN}°，应判可靠`
    );
  }
});

test("非受控光照下弃权机制会真实触发（三种光源至少一次分档不可靠）", () => {
  const base: [number, number, number] = [232, 196, 172];
  const variants = [1.0, 1.06, 0.94].map((warmth) =>
    rgbToLab(
      Math.round(base[0] * warmth),
      base[1],
      Math.round(base[2] * (2 - warmth))
    )
  );
  const reliabilities = variants.map((lab) => classifyItaBandStable(lab).reliable);
  assert.ok(
    reliabilities.some((reliable) => !reliable),
    `三种光源下分档全部可靠，弃权机制未被触发：${reliabilities.join(",")}`
  );
});
