import test from "node:test";
import assert from "node:assert/strict";
import { matchNailDirectionReferences } from "../src/lib/nail-texture-direction.ts";
import { resolveMaskTextureRotation } from "../src/lib/nail-texture-recognition/mask-orientation.ts";

const nail = { cx: 100, cy: 100, length: 60, width: 20, angle: 0 };

test("opposite and mirrored finger directions disambiguate a symmetric square mask", () => {
  const data = new Uint8Array(40 * 80);
  for (let y = 10; y < 70; y++) for (let x = 10; x < 30; x++) data[y * 40 + x] = 1;
  for (const angle of [0, Math.PI]) {
    const [reference] = matchNailDirectionReferences([nail], [{ ...nail, angle }]);
    assert.equal(reference, angle);
    const result = resolveMaskTextureRotation({ width: 40, height: 80, data, originX: 0, originY: 0, scale: 1 }, reference, true);
    assert.equal(result.source, "mask+reference");
    assert.ok(Math.cos(result.rotation - angle) > .99);
    assert.deepEqual(result.warnings, []);
  }
});

test("matching is reciprocal and independent of hand/finger array order", () => {
  const nails = [nail, { ...nail, cx: 160 }];
  const refs = [{ ...nail, cx: 160, angle: Math.PI }, nail];
  assert.deepEqual(matchNailDirectionReferences(nails, refs), [0, Math.PI]);
  assert.deepEqual(nails, [nail, { ...nail, cx: 160 }]);
});

test("close competing fingers, duplicated nails and crossed axes retain review", () => {
  assert.deepEqual(matchNailDirectionReferences([nail], [nail, { ...nail, cx: 102 }]), [null]);
  assert.deepEqual(matchNailDirectionReferences([nail, nail], [nail]), [null, null]);
  assert.deepEqual(matchNailDirectionReferences([nail], [{ ...nail, angle: Math.PI / 2 }]), [null]);
});

test("unrelated, missing and nonfinite reference geometry is rejected", () => {
  for (const refs of [[], [{ ...nail, cx: 300 }], [{ ...nail, length: 0 }], [{ ...nail, angle: NaN }]]) {
    assert.deepEqual(matchNailDirectionReferences([nail], refs), [null]);
  }
});

test("long nail extension allows axial displacement but rejects neighboring finger", () => {
  const extended = { ...nail, cy: 65, length: 100 };
  assert.deepEqual(matchNailDirectionReferences([extended], [nail]), [0]);
  assert.deepEqual(matchNailDirectionReferences([{ ...extended, cx: 120 }], [nail]), [null]);
});
