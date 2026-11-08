// 径向场浏览器移植与权威 Python 实现的对拍测试。
//
// fixture 由 model/training/oneoff/generate-radial-browser-fixtures.py 用权威 Python
// 实现（native-pixel-radial-field.py 的 lattice/fit_radius/logits、
// native-radial-strip-refiner.py 的 build_strip、analyze-saved-nail-roi-coverage.py 的
// crop_box('square_context_035')）确定性生成。
//
// 断言口径：所有 float32 数组（distance/radius/logits/strip）逐元素 === 完全相等。
// 2026-11-05 实测依据：node v24.18.0 对拍探针
// （model/training/oneoff/probe-radial-browser-parity.ts）在本 fixture 上
// bins/distance/radius/logits/strip 共 28896 个元素失配 0、最大绝对差 0，
// V8 Math.atan2/hypot/cos/sin 与 numpy libm 在全部输入上逐位一致，
// 故维持从严断言，无需引入容差。bins 为整数数组，deepStrictEqual 全等。
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import assert from "node:assert/strict";
import test from "node:test";
import {
  computeRadialLattice,
  cropSquareContext035,
  fitRadialRadius,
  radialMaskLogits,
} from "../src/lib/nail-texture-recognition/radial-field.ts";
import { buildRadialStrip } from "../src/lib/nail-texture-recognition/radial-strip.ts";

const fixtureDir = fileURLToPath(new URL("./fixtures/", import.meta.url));
const fieldFixture = JSON.parse(
  readFileSync(fixtureDir + "radial-field-fixture.json", "utf8")
) as RadialFieldFixture;
const stripFixture = JSON.parse(
  readFileSync(fixtureDir + "radial-strip-fixture.json", "utf8")
) as RadialStripFixture;

interface Base64Record {
  dtype: string;
  byteOrder: string;
  shape: number[];
  encoding: string;
  base64: string;
}

interface RadialFieldFixture {
  angularSamples: number;
  shape: number[];
  fieldCases: {
    name: string;
    shape: number[];
    center: [number, number];
    angularSamples: number;
    mask: number[];
    expected: { bins: number[]; distance: Base64Record; radius: Base64Record };
  }[];
  logitsCase: {
    name: string;
    latticeCase: string;
    center: [number, number];
    radius: Base64Record;
    expectedLogits: Base64Record;
  };
  cropBoxCases: {
    name: string;
    box: { x0: number; y0: number; x1: number; y1: number };
    width: number;
    height: number;
    expected: { left: number; top: number; side: number } | null;
  }[];
}

interface RadialStripFixture {
  angularSamples: number;
  radialSamples: number;
  image: { width: number; height: number; channels: string } & Base64Record;
  roi: { x0: number; y0: number; side: number };
  center: [number, number];
  coarse: number[];
  radii: Base64Record;
  expectedStrip: Base64Record;
}

/** base64 的 little-endian float32 解码为 Float32Array（readFloatLE 显式按小端读取）。 */
function decodeF32(record: Base64Record): Float32Array {
  assert.equal(record.dtype, "float32");
  assert.equal(record.byteOrder, "little-endian");
  assert.equal(record.encoding, "base64");
  const bytes = Buffer.from(record.base64, "base64");
  const elementCount = record.shape.reduce((a, b) => a * b, 1);
  assert.equal(bytes.length, elementCount * 4);
  const out = new Float32Array(elementCount);
  for (let i = 0; i < out.length; i++) out[i] = bytes.readFloatLE(i * 4);
  return out;
}

/** float32 逐元素 === 全等断言；失败时报出首个失配下标与两端取值。 */
function assertFloat32Exact(actual: Float32Array, expected: Float32Array, label: string): void {
  assert.equal(actual.length, expected.length, `${label} length`);
  for (let i = 0; i < expected.length; i++) {
    if (actual[i] !== expected[i]) {
      assert.fail(`${label}[${i}]: actual=${actual[i]} expected=${expected[i]}`);
    }
  }
}

/** 由 mask 与 bins 复核「有前景的角度 bin 数」，实证 fit_radius 是否触发环形插值分支。 */
function countKnownBins(mask: Uint8Array, bins: Int32Array, angularSamples: number): number {
  const seen = new Uint8Array(angularSamples);
  let count = 0;
  for (let i = 0; i < mask.length; i++) {
    if (mask[i] === 0 || seen[bins[i]]) continue;
    seen[bins[i]] = 1;
    count++;
  }
  return count;
}

function computeCaseLattice(fieldCase: RadialFieldFixture["fieldCases"][number]) {
  const height = fieldCase.shape[0];
  const width = fieldCase.shape[1];
  assert.equal(width * height, fieldCase.mask.length);
  assert.equal(fieldCase.angularSamples, fieldFixture.angularSamples);
  const lattice = computeRadialLattice(
    width,
    height,
    fieldCase.center[0],
    fieldCase.center[1],
    fieldFixture.angularSamples
  );
  return { width, height, lattice };
}

for (const fieldCase of fieldFixture.fieldCases) {
  test(`radial field case ${fieldCase.name} reproduces lattice/fit_radius bit-exactly`, () => {
    const { width, height, lattice } = computeCaseLattice(fieldCase);

    // bins：整数数组全等。
    assert.deepStrictEqual(Array.from(lattice.bins), fieldCase.expected.bins, `${fieldCase.name} bins`);
    // distance：float32 逐元素 ===。
    assertFloat32Exact(lattice.distance, decodeF32(fieldCase.expected.distance), `${fieldCase.name} distance`);

    const knownBins = countKnownBins(Uint8Array.from(fieldCase.mask), lattice.bins, fieldFixture.angularSamples);
    if (fieldCase.name === "full-coverage") {
      assert.equal(knownBins, fieldFixture.angularSamples);
    } else {
      // 稀疏用例必须存在无前景 bin，实证 fit_radius 走到环形插值分支。
      assert.ok(knownBins > 0 && knownBins < fieldFixture.angularSamples, `knownBins=${knownBins}`);
    }

    const radius = fitRadialRadius(
      Uint8Array.from(fieldCase.mask),
      lattice.bins,
      lattice.distance,
      width,
      height,
      fieldFixture.angularSamples
    );
    assert.ok(radius);
    assertFloat32Exact(radius, decodeF32(fieldCase.expected.radius), `${fieldCase.name} radius`);
  });
}

test("radialMaskLogits reproduces zero-threshold decode bit-exactly", () => {
  const base = fieldFixture.fieldCases.find((c) => c.name === fieldFixture.logitsCase.latticeCase);
  assert.ok(base);
  const { lattice } = computeCaseLattice(base);
  const radius = decodeF32(fieldFixture.logitsCase.radius);
  assert.equal(radius.length, fieldFixture.angularSamples);
  const logits = radialMaskLogits(radius, lattice.bins, lattice.distance);
  assertFloat32Exact(logits, decodeF32(fieldFixture.logitsCase.expectedLogits), "logits");
});

test("buildRadialStrip reproduces build_strip bit-exactly", () => {
  const image = stripFixture.image;
  assert.equal(image.dtype, "uint8");
  assert.equal(image.channels, "RGB");
  assert.equal(image.width * image.height * 3, image.shape.reduce((a, b) => a * b, 1));
  const rgb = Buffer.from(image.base64, "base64");
  const rgba = new Uint8Array(image.width * image.height * 4);
  for (let pixel = 0; pixel < rgba.length / 4; pixel++) {
    rgba[pixel * 4] = rgb[pixel * 3];
    rgba[pixel * 4 + 1] = rgb[pixel * 3 + 1];
    rgba[pixel * 4 + 2] = rgb[pixel * 3 + 2];
    rgba[pixel * 4 + 3] = 255;
  }
  assert.equal(stripFixture.coarse.length, image.width * image.height);
  const radii = decodeF32(stripFixture.radii);
  assert.equal(radii.length, stripFixture.angularSamples);
  const strip = buildRadialStrip(
    { width: image.width, height: image.height, data: rgba },
    stripFixture.roi,
    Uint8Array.from(stripFixture.coarse),
    stripFixture.center[0],
    stripFixture.center[1],
    radii,
    stripFixture.angularSamples
  );
  assert.equal(strip.length, 5 * stripFixture.angularSamples * stripFixture.radialSamples);
  assertFloat32Exact(strip, decodeF32(stripFixture.expectedStrip), "strip");
});

for (const cropCase of fieldFixture.cropBoxCases) {
  test(`cropSquareContext035 case ${cropCase.name}`, () => {
    const actual = cropSquareContext035(cropCase.box, cropCase.width, cropCase.height);
    assert.deepStrictEqual(actual, cropCase.expected);
  });
}
