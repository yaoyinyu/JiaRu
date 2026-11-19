// 跨语言对拍（方案 S5）：运行时 smoothRadiusVector 与 Python 参考实现逐位一致。
//
// fixture 由 model/training/export-runtime-radius-smoothing-parity-fixture.py 生成：
// 16 枚半径向量取自 634 冻结预测 mask 的最大外轮廓（按运行时 bin 原点重拟合），
// 每枚带几何（height/width/center）与 Python 侧算出的解码指纹。
// 门：本文件全部断言通过 = 差异 0 像素；任一 case 指纹不一致即说明运行时与
// 证据侧实现分叉，必须先修再谈接入（方案 §8 L2）。

import { readFileSync } from "node:fs";
import { createHash } from "node:crypto";
import { fileURLToPath } from "node:url";
import assert from "node:assert/strict";
import test from "node:test";
import { computeRadialLattice, radialMaskLogits } from "../src/lib/nail-texture-recognition/radial-field.ts";
import { smoothRadiusVector } from "../src/lib/nail-texture-recognition/radial-smoothing.ts";

interface FixtureCase {
  index: number;
  sourceOrdinal: number;
  truthIndex: number;
  fileName: string;
  height: number;
  width: number;
  centerY: number;
  centerX: number;
  angularSamples: number;
  area: number;
  reconstructionIoU: number;
  radius: { dtype: string; byteOrder: string; encoding: string; base64: string };
  expected: {
    applied: boolean;
    sigmaArcPixels: number;
    areaCompensationPixels: number;
    areaBefore: number;
    areaAfter: number;
    sha256Before: string;
    sha256After: string;
  };
}

interface Fixture {
  schemaVersion: number;
  name: string;
  recipe: {
    smoothing: {
      mode: "rms-bounded-gaussian";
      deviationRmsArcPixels: number;
      gridArcPixels: number[];
      areaCompensation: boolean;
    };
  };
  selection: { count: number; appliedCount: number };
  cases: FixtureCase[];
}

const fixtureDirectory = fileURLToPath(new URL("./fixtures/", import.meta.url));
const fixture = JSON.parse(readFileSync(fixtureDirectory + "radius-smoothing-parity-v1.json", "utf8")) as Fixture;

/** 与导出脚本同一口径：布尔 mask 按行主序按位打包（bit i → byte i>>3 的第 i&7 位）后 sha256。 */
function maskDigest(mask: Uint8Array): string {
  const packed = new Uint8Array(Math.ceil(mask.length / 8));
  for (let index = 0; index < mask.length; index += 1) {
    if (mask[index]) packed[index >> 3] |= 1 << (index & 7);
  }
  return createHash("sha256").update(packed).digest("hex");
}

function decodeMask(radius: Float32Array, bins: Int32Array, distance: Float32Array): Uint8Array {
  const logits = radialMaskLogits(radius, bins, distance);
  const mask = new Uint8Array(logits.length);
  for (let index = 0; index < logits.length; index += 1) mask[index] = logits[index] >= 0 ? 1 : 0;
  return mask;
}

function decodeRadius(case_: FixtureCase): Float32Array {
  const buffer = Buffer.from(case_.radius.base64, "base64");
  assert.equal(buffer.byteLength, case_.angularSamples * 4, `case ${case_.index} 半径向量字节数不符`);
  const copy = new Float32Array(case_.angularSamples);
  for (let index = 0; index < case_.angularSamples; index += 1) {
    copy[index] = buffer.readFloatLE(index * 4);
  }
  return copy;
}

test("parity fixture covers both smoothing-applied and no-op cases", () => {
  assert.equal(fixture.schemaVersion, 1);
  assert.equal(fixture.cases.length, fixture.selection.count);
  assert.ok(fixture.cases.length >= 8, "样本数不足，无法代表半径尺度分布");
  const applied = fixture.cases.filter((entry) => entry.expected.applied).length;
  assert.equal(applied, fixture.selection.appliedCount);
  assert.ok(applied > 0, "全部 case 都不触发平滑，对拍失去意义");
});

test("runtime smoothing reproduces the Python reference bit-exactly on every case", () => {
  const recipe = fixture.recipe.smoothing;
  const failures: string[] = [];
  let applied = 0;

  for (const case_ of fixture.cases) {
    const radius = decodeRadius(case_);
    const lattice = computeRadialLattice(
      case_.width,
      case_.height,
      case_.centerX,
      case_.centerY,
      case_.angularSamples
    );

    // 平滑前：验证 lattice 与零阈值解码口径一致（bin 原点、float32 距离）。
    const before = decodeMask(radius, lattice.bins, lattice.distance);
    if (maskDigest(before) !== case_.expected.sha256Before) {
      failures.push(`case ${case_.index} 平滑前指纹不一致（lattice/解码口径分叉）`);
      continue;
    }

    const smoothing = smoothRadiusVector(radius, lattice.bins, lattice.distance, {
      mode: recipe.mode,
      deviationRmsArcPixels: recipe.deviationRmsArcPixels,
      gridArcPixels: recipe.gridArcPixels,
      areaCompensation: recipe.areaCompensation,
    });

    if (smoothing.applied !== case_.expected.applied) {
      failures.push(`case ${case_.index} applied=${smoothing.applied} 与参考 ${case_.expected.applied} 不符`);
      continue;
    }
    if (smoothing.sigmaArcPixels !== case_.expected.sigmaArcPixels) {
      failures.push(
        `case ${case_.index} sigma=${smoothing.sigmaArcPixels} 与参考 ${case_.expected.sigmaArcPixels} 不符`
      );
      continue;
    }
    if (Math.abs(smoothing.areaCompensationPixels - case_.expected.areaCompensationPixels) > 1e-6) {
      failures.push(
        `case ${case_.index} 面积补偿 ${smoothing.areaCompensationPixels} 与参考 ${case_.expected.areaCompensationPixels} 不符`
      );
      continue;
    }
    if (smoothing.applied) applied += 1;

    const after = decodeMask(smoothing.radius, lattice.bins, lattice.distance);
    if (maskDigest(after) !== case_.expected.sha256After) {
      failures.push(`case ${case_.index} 平滑后指纹不一致`);
      continue;
    }

    const areaBefore = before.reduce((total: number, value: number) => total + value, 0);
    const areaAfter = after.reduce((total: number, value: number) => total + value, 0);
    if (areaBefore !== case_.expected.areaBefore) {
      failures.push(`case ${case_.index} 平滑前面积 ${areaBefore} 与参考 ${case_.expected.areaBefore} 不符`);
    }
    if (areaAfter !== case_.expected.areaAfter) {
      failures.push(`case ${case_.index} 平滑后面积 ${areaAfter} 与参考 ${case_.expected.areaAfter} 不符`);
    }
  }

  assert.equal(failures.length, 0, `跨语言对拍失败 ${failures.length} 例：\n${failures.join("\n")}`);
  assert.equal(applied, fixture.selection.appliedCount);
});

test("area compensation keeps the decoded area equal to the pre-smoothing area", () => {
  const recipe = fixture.recipe.smoothing;
  const offenders: string[] = [];
  for (const case_ of fixture.cases) {
    if (!case_.expected.applied) continue;
    const delta = case_.expected.areaAfter - case_.expected.areaBefore;
    const relative = Math.abs(delta) / Math.max(1, case_.expected.areaBefore);
    if (relative > 0.005) {
      offenders.push(`case ${case_.index} 面积相对变化 ${(relative * 100).toFixed(3)}%`);
    }
  }
  assert.equal(offenders.length, 0, offenders.join("\n"));
  assert.ok(recipe.areaCompensation);
});
