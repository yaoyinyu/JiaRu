import test from "node:test";
import assert from "node:assert/strict";
import { matchNailDirectionReferences, matchNailDirectionsByFinger } from "../src/lib/nail-texture-direction.ts";
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

test("same-finger reference gives tip direction without geometric pairing", () => {
  const hand = { ...nail, id: "mediapipe-hand-0-finger-0", angle: 0 };
  assert.deepEqual(matchNailDirectionsByFinger([{ ...nail, finger: 0 }], [hand]), [0]);
  // 手指朝下时甲尖也朝下，方向随参考角变化
  assert.deepEqual(
    matchNailDirectionsByFinger([{ ...nail, finger: 3 }], [{ ...nail, id: "mediapipe-hand-0-finger-3", angle: Math.PI }]),
    [Math.PI],
  );
});

test("finger direction is rejected when the reference sits on another nail", () => {
  const farAway = { ...nail, cx: 400, cy: 400, id: "mediapipe-hand-0-finger-2" };
  assert.deepEqual(matchNailDirectionsByFinger([{ ...nail, finger: 2 }], [farAway]), [null]);
  const wrongAxis = { ...nail, cx: 100, cy: 300, id: "mediapipe-hand-0-finger-2" };
  assert.deepEqual(matchNailDirectionsByFinger([{ ...nail, finger: 2 }], [wrongAxis]), [null]);
});

test("unassigned finger, unparsable reference id and nonfinite geometry stay unresolved", () => {
  const hand = { ...nail, id: "mediapipe-hand-0-finger-1", angle: 0 };
  assert.deepEqual(matchNailDirectionsByFinger([{ ...nail, finger: null }], [hand]), [null]);
  assert.deepEqual(matchNailDirectionsByFinger([{ ...nail, finger: 1 }], [{ ...nail }]), [null]);
  assert.deepEqual(
    matchNailDirectionsByFinger([{ ...nail, finger: 1 }], [{ ...nail, id: "mediapipe-hand-0-finger-1", angle: NaN }]),
    [null],
  );
});

test("two hands exposing the same finger prefer the nearest reference", () => {
  const left = { ...nail, cx: 97, cy: 100, id: "mediapipe-hand-0-finger-2", angle: 0 };
  const right = { ...nail, cx: 260, cy: 100, id: "mediapipe-hand-1-finger-2", angle: Math.PI };
  assert.deepEqual(matchNailDirectionsByFinger([{ ...nail, finger: 2 }], [right, left]), [0]);
  assert.deepEqual(matchNailDirectionsByFinger([{ ...nail, cx: 260, finger: 2 }], [right, left]), [Math.PI]);
});
