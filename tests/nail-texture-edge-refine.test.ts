import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { radialCoverageAlpha } from "../src/lib/nail-texture-recognition/edge-refine.ts";
import { buildFeatheredAlphaMask, findMaskBounds } from "../src/lib/nail-texture-recognition/extract-mask-texture.ts";
import { validateNailTextureModelManifest } from "../src/lib/nail-texture-recognition/model-runtime.ts";

const fixture = JSON.parse(readFileSync(new URL("./fixtures/radial-coverage-v1.json", import.meta.url), "utf8")) as {
  cases: { name: string; width: number; height: number; center: number[]; radius: number[]; hard: number[]; alpha2: number[]; alpha4: number[] }[];
};
for (const row of fixture.cases) {
  test(`radial coverage matches Python bytes: ${row.name}`, () => {
    const radius = Float32Array.from(row.radius), hard = Uint8Array.from(row.hard);
    const radiusBefore = radius.slice(), hardBefore = hard.slice();
    for (const samples of [2, 4] as const) {
      assert.deepEqual(radialCoverageAlpha(radius, row.center[0], row.center[1], hard, row.width, row.height, samples), Uint8ClampedArray.from(samples === 2 ? row.alpha2 : row.alpha4));
    }
    assert.deepEqual(radius, radiusBefore);
    assert.deepEqual(hard, hardBefore);
  });
}

test("coverage validates its geometry inputs", () => {
  const radius = new Float32Array(128).fill(2);
  assert.throws(() => radialCoverageAlpha(radius, 1, 1, new Uint8Array(2), 3, 3), /invalid_radial_coverage/);
  radius[0] = NaN;
  assert.throws(() => radialCoverageAlpha(radius, 1, 1, new Uint8Array(9), 3, 3), /invalid_radial_coverage/);
});

test("coverage keeps exterior partial pixels and bypasses inward feathering", () => {
  const mask = { width: 3, height: 1, data: Uint8Array.from([0, 1, 0]), originX: 0, originY: 0, scale: 1, coverageAlpha: Uint8ClampedArray.from([32, 240, 16]) };
  assert.deepEqual(findMaskBounds(mask), { minX: 1, maxX: 1, minY: 0, maxY: 0 });
  assert.deepEqual(findMaskBounds(mask, true), { minX: 0, maxX: 2, minY: 0, maxY: 0 });
  const alpha = buildFeatheredAlphaMask(mask, 2);
  assert.deepEqual(alpha, mask.coverageAlpha);
  alpha[0] = 0;
  assert.equal(mask.coverageAlpha[0], 32);
  assert.throws(() => buildFeatheredAlphaMask({ ...mask, coverageAlpha: new Uint8ClampedArray(1) }), /coverage_alpha_shape_mismatch/);
});

test("manifest accepts only versioned coverage profiles with supported sampling", () => {
  const manifest = JSON.parse(readFileSync(new URL("../public/models/nail-texture-seg/manifest.json", import.meta.url), "utf8"));
  for (const samples of [2, 4]) {
    const value = { ...manifest, stage2: { ...manifest.stage2, edgeRefinement: { mode: "radial-coverage-v1", samples } } };
    assert.deepEqual(validateNailTextureModelManifest(value), []);
  }
  for (const edgeRefinement of [null, {}, { mode: "unknown", samples: 4 }, { mode: "radial-coverage-v1", samples: 3 }, { mode: "radial-coverage-v1", samples: "4" }]) {
    assert.ok(validateNailTextureModelManifest({ ...manifest, stage2: { ...manifest.stage2, edgeRefinement } }).includes("manifest_stage2_edge_refinement_invalid"));
  }
});
