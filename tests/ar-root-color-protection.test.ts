import assert from "node:assert/strict";
import test from "node:test";
import {
  adaptiveRootProtectionWeight,
  blendProtectedRootOutputs,
  buildSquareOpacityMask,
  buildTextureAreaIntegral,
  createExactAreaSampler,
  minimumPixelFootprint,
  multiplyAffine,
  renderProtectedRootColors,
  textureLayerToPhysicalMatrix,
  textureLayerToScreenMatrix,
  textureLayerToSourceMatrix,
} from "../src/lib/ar-root-color-protection.ts";

function plane(width: number, height: number, fill: [number, number, number, number] = [100, 110, 120, 255]) {
  const data = new Uint8ClampedArray(width * height * 4);
  for (let i = 0; i < data.length; i += 4) data.set(fill, i);
  return { width, height, data };
}

test("affine composition follows matrix multiplication and inverse mapping", () => {
  const left = { a: 2, b: 0, c: 0, d: 3, e: 10, f: 20 };
  const right = { a: 1, b: .5, c: -.25, d: 1, e: 4, f: -2 };
  const composed = multiplyAffine(left, right);
  assert.equal(composed.a, 2);
  assert.equal(composed.b, 1.5);
  assert.equal(composed.c, -.5);
  assert.equal(composed.d, 3);
  assert.equal(composed.e, 18);
  assert.equal(composed.f, 14);
});

test("layer pixels map to source coordinates through the production draw rectangle", () => {
  const matrix = textureLayerToSourceMatrix(
    { x: -14, y: -26, width: 40, height: 60 }, 20, 30, 60, 70,
  );
  assert.ok(matrix);
  assert.ok(Math.abs(matrix.a - .5) < 1e-12);
  assert.ok(Math.abs(matrix.d - .5) < 1e-12);
  assert.ok(Math.abs(matrix.e - (-8)) < 1e-12);
  assert.ok(Math.abs(matrix.f - (-4.5)) < 1e-12);
  assert.ok(Math.abs(matrix.a * 30 + matrix.e - 7) < 1e-12);
  assert.ok(Math.abs(matrix.d * 35 + matrix.f - 13) < 1e-12);
});

test("layer-to-screen and physical mappings preserve center and device ratio", () => {
  const geometry = { a: 1, b: 0, c: 0, d: 1, e: 100, f: 200 };
  const screen = textureLayerToScreenMatrix(geometry, 20, 10);
  assert.ok(Math.abs(screen.a * 10 + screen.c * 5 + screen.e - 100) < 1e-12);
  assert.ok(Math.abs(screen.b * 10 + screen.d * 5 + screen.f - 200) < 1e-12);
  assert.ok(Math.abs(screen.a * 0 + screen.c * 0 + screen.e - 90) < 1e-12);
  assert.ok(Math.abs(screen.b * 0 + screen.d * 0 + screen.f - 195) < 1e-12);
  const physical = textureLayerToPhysicalMatrix(geometry, 20, 10, 2);
  assert.ok(physical);
  assert.ok(Math.abs(physical.a - 2) < 1e-12);
  assert.ok(Math.abs(physical.d - 2) < 1e-12);
  assert.ok(Math.abs(physical.a * 10 + physical.c * 5 + physical.e - 200) < 1e-12);
});

test("exact area integral reproduces identity and downsampling references", () => {
  const width = 8, height = 6;
  const rgb = new Uint8Array(width * height * 3);
  for (let i = 0; i < width * height; i++) {
    rgb[3 * i] = (i * 17) % 256;
    rgb[3 * i + 1] = (i * 31 + 5) % 256;
    rgb[3 * i + 2] = (i * 43 + 11) % 256;
  }
  const integral = buildTextureAreaIntegral(rgb, width, height, { minX: 0, minY: 0, maxX: width - 1, maxY: height - 1 });
  const identity = createExactAreaSampler(integral, { a: 1, b: 0, c: 0, d: 1, e: 0, f: 0 });
  for (let y = 0; y < height; y++) for (let x = 0; x < width; x++) {
    const expected = [rgb[3 * (y * width + x)], rgb[3 * (y * width + x) + 1], rgb[3 * (y * width + x) + 2]];
    assert.deepEqual(Array.from(identity(x, y)), expected);
  }
  const down = createExactAreaSampler(integral, { a: 2, b: 0, c: 0, d: 2, e: 0, f: 0 });
  for (let y = 0; y < 3; y++) for (let x = 0; x < 4; x++) {
    const actual = down(x, y);
    for (let c = 0; c < 3; c++) {
      let expected = 0;
      for (let dy = 0; dy < 2; dy++) for (let dx = 0; dx < 2; dx++) {
        expected += rgb[3 * ((2 * y + dy) * width + 2 * x + dx) + c];
      }
      assert.ok(Math.abs(actual[c] - expected / 4) < 1e-7);
    }
  }
});

test("exact area integral keeps constant energy under rotation and mirror", () => {
  const width = 11, height = 9;
  const rgb = new Uint8Array(width * height * 3).fill(106);
  const integral = buildTextureAreaIntegral(rgb, width, height, { minX: 0, minY: 0, maxX: width - 1, maxY: height - 1 });
  const rotations = [0, .23, .78, Math.PI / 2, -.46, 2.41];
  for (const angle of rotations) {
    const cos = Math.cos(angle), sin = Math.sin(angle);
    for (const scales of [[.2, .83], [.5, 2.1], [1, 1], [2.8, 3.4], [-1.9, .9]]) {
      const matrix = {
        a: cos * scales[0], b: sin * scales[0],
        c: -sin * scales[1], d: cos * scales[1],
        e: 5.28, f: 4.13,
      };
      const sampled = createExactAreaSampler(integral, matrix)(0, 0);
      for (let c = 0; c < 3; c++) assert.ok(Math.abs(sampled[c] - 106) < 1e-7);
    }
  }
});

test("square opacity masks preserve 1px and 2px neighborhood semantics", () => {
  const width = 7, height = 7;
  const rgba = new Uint8ClampedArray(width * height * 4);
  for (let i = 0; i < rgba.length; i += 4) rgba[i + 3] = 255;
  rgba[4 * (3 * width + 3) + 3] = 60;
  const one = buildSquareOpacityMask(rgba, width, height, 1);
  assert.equal(one[4 * (3 * width + 3) + 3], 0);
  assert.equal(one[4 * (3 * width + 2) + 3], 0);
  assert.equal(one[4 * (1 * width + 1) + 3], 255);
  assert.equal(one[4 * (0 * width + 0) + 3], 0, "保护层边框保持透明");
  assert.equal(one.filter((_, i) => i % 4 === 3 && _ === 255).length, 16);

  const wide = 13, tall = 13;
  const wideRgba = new Uint8ClampedArray(wide * tall * 4);
  for (let i = 0; i < wideRgba.length; i += 4) wideRgba[i + 3] = 255;
  wideRgba[4 * (3 * wide + 3) + 3] = 60;
  const two = buildSquareOpacityMask(wideRgba, wide, tall, 2);
  assert.equal(two[4 * (3 * wide + 3) + 3], 0);
  assert.equal(two[4 * (3 * wide + 1) + 3], 0);
  assert.equal(two[4 * (8 * wide + 8) + 3], 255);
  assert.equal(two.filter((_, i) => i % 4 === 3 && _ === 255).length, 65);
});

test("root color replacement stays in the root band and keeps alpha bytes", () => {
  const base = plane(7, 7);
  const direct = plane(7, 7);
  base.data.set([150, 150, 150, 255], 4 * (3 * 7 + 3));
  const before = Uint8ClampedArray.from(base.data);
  const sampler = () => new Float64Array([200, 200, 200]);
  const guarded = renderProtectedRootColors(base, direct, 4, sampler);
  const center = 4 * (4 * 7 + 3);
  assert.equal(guarded[center], 107);
  assert.equal(guarded[center + 1], 116);
  assert.equal(guarded[center + 2], 125);
  assert.equal(guarded[center + 3], 255);
  assert.equal(guarded[4 * (2 * 7 + 3)], before[4 * (2 * 7 + 3)]);
  assert.equal(guarded[4 * (4 * 7 + 3) + 3], before[4 * (4 * 7 + 3) + 3]);
});

test("root color replacement skips pixels removed by the protected direct layer", () => {
  const base = plane(7, 7);
  const direct = plane(7, 7);
  direct.data[4 * (4 * 7 + 3) + 3] = 0;
  const before = Uint8ClampedArray.from(base.data);
  const guarded = renderProtectedRootColors(base, direct, 4, () => new Float64Array([255, 255, 255]));
  const center = 4 * (4 * 7 + 3);
  assert.equal(guarded[center], before[center]);
  assert.equal(guarded[center + 1], before[center + 1]);
  assert.equal(guarded[center + 2], before[center + 2]);
});

test("protected output blending is monotonic and rejects alpha drift", () => {
  const primary = plane(3, 3, [10, 20, 30, 255]);
  const extended = plane(3, 3, [30, 40, 50, 255]);
  const half = blendProtectedRootOutputs(primary, extended, .5);
  assert.equal(half[0], 20);
  assert.equal(half[1], 30);
  assert.equal(half[2], 40);
  assert.equal(half[3], 255);
  assert.equal(blendProtectedRootOutputs(primary, extended, 0)[0], 10);
  assert.equal(blendProtectedRootOutputs(primary, extended, 1)[0], 30);
  extended.data[3] = 128;
  assert.throws(() => blendProtectedRootOutputs(primary, extended, .5), /alpha_mismatch/u);
});

test("physical footprint and adaptive weight match the V7 thresholds", () => {
  assert.equal(adaptiveRootProtectionWeight(1), 0);
  assert.equal(adaptiveRootProtectionWeight(2), 0);
  assert.equal(adaptiveRootProtectionWeight(3), 1);
  assert.ok(adaptiveRootProtectionWeight(2.5) > 0);
  assert.ok(adaptiveRootProtectionWeight(2.5) < 1);
  assert.equal(adaptiveRootProtectionWeight(Number.NaN), 0);
  const identity = minimumPixelFootprint({ a: 1, b: 0, c: 0, d: 1, e: 0, f: 0 });
  assert.ok(Math.abs(identity! - 1) < 1e-12);
  const narrow = minimumPixelFootprint({ a: .25, b: 0, c: 0, d: 2, e: 0, f: 0 });
  assert.ok(Math.abs(narrow! - .25) < 1e-12);
  assert.equal(minimumPixelFootprint({ a: 0, b: 0, c: 0, d: 0, e: 0, f: 0 }), null);
});
