import assert from "node:assert/strict";
import test from "node:test";

import {
  approximateMonkGrade,
  classifyItaBand,
  classifyUndertone,
  individualTypologyAngle,
  ITA_BAND_BOUNDS,
  labDistance,
  rgbToLab,
  UNDERTONE_COOL_B_LOW,
  UNDERTONE_OLIVE_A,
  UNDERTONE_WARM_B,
} from "../src/lib/nail-personalization/color-science.ts";

test("rgbToLab 对白/黑/中灰给出标准 CIELAB 值", () => {
  const white = rgbToLab(255, 255, 255);
  assert.ok(Math.abs(white.L - 100) < 0.5, `white L=${white.L}`);
  assert.ok(Math.abs(white.a) < 0.5, `white a=${white.a}`);
  assert.ok(Math.abs(white.b) < 0.5, `white b=${white.b}`);

  const black = rgbToLab(0, 0, 0);
  assert.ok(Math.abs(black.L - 0) < 0.5, `black L=${black.L}`);

  const gray = rgbToLab(128, 128, 128);
  assert.ok(Math.abs(gray.L - 53.585) < 0.6, `gray L=${gray.L}`);
  assert.ok(Math.abs(gray.a) < 0.5 && Math.abs(gray.b) < 0.5);
});

test("rgbToLab 越界输入按 0-255 截断，不抛错", () => {
  const clamped = rgbToLab(300, -20, 128);
  assert.ok(Number.isFinite(clamped.L) && Number.isFinite(clamped.a) && Number.isFinite(clamped.b));
  assert.ok(clamped.L >= 0 && clamped.L <= 100);
});

test("individualTypologyAngle 与 ITA° 定义一致，b*=0 时按极限处理", () => {
  const ita = individualTypologyAngle({ L: 60, a: 0, b: 15 });
  const expected = (Math.atan(10 / 15) * 180) / Math.PI;
  assert.ok(Math.abs(ita - expected) < 1e-9);

  assert.equal(individualTypologyAngle({ L: 60, a: 0, b: 0 }), 90);
  assert.equal(individualTypologyAngle({ L: 40, a: 0, b: 0 }), -90);
  assert.equal(individualTypologyAngle({ L: 50, a: 0, b: 0 }), 0);
});

test("classifyItaBand 采用左开右闭，边界值归属明确", () => {
  assert.equal(classifyItaBand(ITA_BAND_BOUNDS[0] + 0.001), "very-light");
  assert.equal(classifyItaBand(ITA_BAND_BOUNDS[0]), "light");
  assert.equal(classifyItaBand(ITA_BAND_BOUNDS[1]), "intermediate");
  assert.equal(classifyItaBand(ITA_BAND_BOUNDS[2]), "tan");
  assert.equal(classifyItaBand(ITA_BAND_BOUNDS[3]), "brown");
  assert.equal(classifyItaBand(ITA_BAND_BOUNDS[4]), "dark");
  assert.equal(classifyItaBand(ITA_BAND_BOUNDS[4] - 0.001), "dark");
  assert.equal(classifyItaBand(0), "brown");
});

test("approximateMonkGrade 随 ITA° 下降单调不减，且落在 1-10", () => {
  let previous = 0;
  for (let l = 100; l >= 0; l -= 5) {
    const grade = approximateMonkGrade({ L: l, a: 0, b: 10 });
    assert.ok(grade >= 1 && grade <= 10, `grade=${grade}`);
    assert.ok(grade >= previous, `L=${l} grade=${grade} < previous=${previous}`);
    previous = grade;
  }
  assert.equal(approximateMonkGrade({ L: 100, a: 0, b: 5 }), 1);
  assert.equal(approximateMonkGrade({ L: 10, a: 0, b: 5 }), 10);
});

test("classifyUndertone 四值与优先级边界（橄榄优先于暖）", () => {
  assert.equal(classifyUndertone({ L: 60, a: 0, b: UNDERTONE_WARM_B + 1 }), "warm");
  assert.equal(classifyUndertone({ L: 60, a: -5, b: UNDERTONE_COOL_B_LOW - 1 }), "cool");
  assert.equal(classifyUndertone({ L: 60, a: UNDERTONE_OLIVE_A + 1, b: 10 }), "olive");
  assert.equal(classifyUndertone({ L: 60, a: 0, b: 8 }), "neutral");
  // a*>2 且 b*>14 同时成立：按优先级判橄榄，消除空洞。
  assert.equal(classifyUndertone({ L: 60, a: 3, b: 20 }), "olive");
});

test("labDistance 为 ΔE76", () => {
  assert.ok(Math.abs(labDistance({ L: 0, a: 0, b: 0 }, { L: 3, a: 4, b: 0 }) - 5) < 1e-9);
  assert.equal(labDistance({ L: 50, a: 0, b: 0 }, { L: 50, a: 0, b: 0 }), 0);
});
