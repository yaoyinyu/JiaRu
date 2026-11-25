import assert from "node:assert/strict";
import test from "node:test";
import {
  appendRegionsForUnmatchedReferences,
  assignFingersFromFingerTips,
  assignFingersFromHandGeometry,
  dedupeRegionsByFinger,
  filterRegionsByFingertipSupport,
  parseHandReferenceId,
  type FingerAssignmentReference,
  type FingerAssignmentRegion,
  type FingerTipReference,
} from "../src/lib/nail-finger-assignment.ts";

function region(
  id: string,
  cx: number,
  cy: number,
  assignedFinger: number | null,
  confidence: FingerAssignmentRegion["confidence"] = "high"
): FingerAssignmentRegion {
  return { id, cx, cy, nl: 60, nw: 40, angle: 0, assignedFinger, confidence };
}

function reference(finger: number, cx: number, cy: number, handIndex = 0): FingerAssignmentReference {
  return {
    id: `mediapipe-hand-${handIndex}-finger-${finger}`,
    cx,
    cy,
    length: 60,
    width: 40,
    angle: 0,
    finger,
  };
}

test("parseHandReferenceId reads hand index and finger", () => {
  assert.deepEqual(parseHandReferenceId("mediapipe-hand-1-finger-3"), { handIndex: 1, finger: 3 });
  assert.equal(parseHandReferenceId("mediapipe-hand-0-finger-7"), null);
  assert.equal(parseHandReferenceId("model-candidate-2"), null);
  assert.equal(parseHandReferenceId(undefined), null);
});

test("hand geometry overrides rank-based placeholder fingers", () => {
  // 排名占位值把中指那枚甲面标成拇指；几何参考应改回真实指位。
  const regions = [region("a", 300, 100, 0), region("b", 500, 100, 1)];
  const references = [
    reference(0, 100, 100),
    reference(1, 200, 100),
    reference(2, 300, 100),
    reference(3, 400, 100),
    reference(4, 500, 100),
  ];

  const { regions: assigned, matches } = assignFingersFromHandGeometry(regions, references);

  assert.equal(assigned[0].assignedFinger, 2);
  assert.equal(assigned[1].assignedFinger, 4);
  assert.equal(matches.length, 2);
});

test("hand geometry leaves regions outside the match gate untouched", () => {
  const regions = [region("far", 2000, 2000, 3)];
  const references = [reference(1, 100, 100)];

  const { regions: assigned, matches } = assignFingersFromHandGeometry(regions, references);

  assert.equal(assigned[0].assignedFinger, 3);
  assert.equal(matches.length, 0);
});

test("hand geometry keeps one-to-one matching when candidates overlap", () => {
  const regions = [region("first", 300, 100, 0), region("second", 305, 102, 1)];
  const references = [reference(2, 300, 100)];

  const { regions: assigned, matches } = assignFingersFromHandGeometry(regions, references);

  assert.equal(matches.length, 1);
  assert.equal(matches[0].regionId, "first");
  assert.equal(assigned[0].assignedFinger, 2);
  assert.equal(assigned[1].assignedFinger, 1);
});

test("hand geometry matches the nearer hand when both hands are visible", () => {
  const regions = [region("right-hand", 900, 100, null), region("left-hand", 100, 100, null)];
  const references = [
    reference(1, 100, 100, 0),
    reference(1, 900, 100, 1),
    reference(4, 120, 100, 0),
  ];

  const { regions: assigned } = assignFingersFromHandGeometry(regions, references);

  assert.equal(assigned[1].assignedFinger, 1);
  assert.equal(assigned[0].assignedFinger, 1);
});

test("finger tips assign fingers even without dorsum geometry", () => {
  const regions = [region("a", 100, 100, 0), region("b", 200, 100, 1)];
  // 指尖 y=73、方向朝上：甲面中心期望在指尖后方 0.45×60≈27 像素，即 y≈100。
  const tips: FingerTipReference[] = [
    { id: "tip-0", finger: 0, cx: 100, cy: 73, dirX: 0, dirY: -1 },
    { id: "tip-2", finger: 2, cx: 200, cy: 73, dirX: 0, dirY: -1 },
  ];

  const { regions: assigned, matches } = assignFingersFromFingerTips(regions, tips);

  assert.equal(assigned[0].assignedFinger, 0);
  assert.equal(assigned[1].assignedFinger, 2);
  assert.equal(matches.length, 2);
});

test("finger tips reject regions more than one nail length away", () => {
  const regions = [region("far", 100, 300, 3)];
  const tips: FingerTipReference[] = [
    { id: "tip-1", finger: 1, cx: 100, cy: 73, dirX: 0, dirY: -1 },
  ];

  const { regions: assigned, matches } = assignFingersFromFingerTips(regions, tips);

  assert.equal(assigned[0].assignedFinger, 3);
  assert.equal(matches.length, 0);
});

test("fingertip support removes candidates far from every fingertip", () => {
  const regions = [region("near", 100, 100, null), region("far", 400, 400, null)];
  const tips: FingerTipReference[] = [
    { id: "tip-0", finger: 0, cx: 100, cy: 100, dirX: 0, dirY: -1 },
    { id: "tip-1", finger: 1, cx: 200, cy: 100, dirX: 0, dirY: -1 },
    { id: "tip-2", finger: 2, cx: 300, cy: 100, dirX: 0, dirY: -1 },
  ];

  const { regions: kept, removed } = filterRegionsByFingertipSupport(regions, tips);

  assert.deepEqual(kept.map((item) => item.id), ["near"]);
  assert.deepEqual(removed.map((item) => item.id), ["far"]);
});

test("fingertip support stays inactive when tips do not cover all regions", () => {
  const regions = [
    region("a", 100, 100, null),
    region("b", 200, 100, null),
    region("c", 400, 400, null),
    region("d", 500, 500, null),
  ];
  const tips: FingerTipReference[] = [
    { id: "tip-0", finger: 0, cx: 100, cy: 100, dirX: 0, dirY: -1 },
    { id: "tip-1", finger: 1, cx: 200, cy: 100, dirX: 0, dirY: -1 },
    { id: "tip-2", finger: 2, cx: 300, cy: 100, dirX: 0, dirY: -1 },
  ];

  const { regions: kept, removed } = filterRegionsByFingertipSupport(regions, tips);

  assert.equal(kept.length, 4);
  assert.equal(removed.length, 0);
});

test("unmatched hand references add a review region for the missing finger", () => {
  const regions = [region("a", 100, 100, 0)];
  const references = [reference(0, 100, 100), reference(2, 300, 300)];

  const { regions: next, added } = appendRegionsForUnmatchedReferences(
    regions,
    references,
    (ref) => ({
      id: `${ref.id}-fill`,
      cx: ref.cx,
      cy: ref.cy,
      nl: ref.length,
      nw: ref.width,
      angle: ref.angle,
      assignedFinger: ref.finger,
      confidence: "low" as const,
    })
  );

  assert.equal(added.length, 1);
  assert.equal(added[0].assignedFinger, 2);
  assert.equal(next.length, 2);
});

test("dedupeRegionsByFinger keeps the higher confidence region per finger", () => {
  const regions = [
    region("low", 100, 100, 2, "low"),
    region("high", 120, 100, 2, "high"),
    region("other", 300, 100, 3, "medium"),
    region("manual", 400, 100, null, "high"),
  ];

  const { regions: kept, removed } = dedupeRegionsByFinger(regions);

  assert.deepEqual(kept.map((item) => item.id), ["high", "other", "manual"]);
  assert.deepEqual(removed.map((item) => item.id), ["low"]);
});

test("dedupeRegionsByFinger preserves order for equal confidence", () => {
  const regions = [region("a", 100, 100, 1), region("b", 200, 100, 1)];

  const { regions: kept, removed } = dedupeRegionsByFinger(regions);

  assert.deepEqual(kept.map((item) => item.id), ["a"]);
  assert.deepEqual(removed.map((item) => item.id), ["b"]);
});
