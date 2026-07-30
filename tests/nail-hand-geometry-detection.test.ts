import assert from "node:assert/strict";
import test from "node:test";
import {
  createNailCandidatesFromHandGeometry,
} from "../src/lib/nail-hand-geometry-detection.ts";
import type { NailLandmark } from "../src/lib/nail-geometry.ts";

function createDorsumLandmarks(): NailLandmark[] {
  const points = Array.from({ length: 21 }, () => ({ x: 0.5, y: 0.7, z: 0 }));
  points[0] = { x: 0.5, y: 0.88, z: 0 };
  points[5] = { x: 0.67, y: 0.62, z: 0 };
  points[9] = { x: 0.54, y: 0.58, z: 0 };
  points[13] = { x: 0.43, y: 0.6, z: 0 };
  points[17] = { x: 0.38, y: 0.65, z: 0 };

  const fingerPoints = [
    { pip: 2, dip: 3, tip: 4, x: 0.75 },
    { pip: 6, dip: 7, tip: 8, x: 0.66 },
    { pip: 10, dip: 11, tip: 12, x: 0.54 },
    { pip: 14, dip: 15, tip: 16, x: 0.43 },
    { pip: 18, dip: 19, tip: 20, x: 0.34 },
  ];
  for (const finger of fingerPoints) {
    points[finger.pip] = { x: finger.x, y: 0.5, z: 0 };
    points[finger.dip] = { x: finger.x, y: 0.35, z: 0 };
    points[finger.tip] = { x: finger.x, y: 0.2, z: 0 };
  }
  return points;
}

test("hand geometry automatically creates five finger-assigned nail candidates", () => {
  const result = createNailCandidatesFromHandGeometry(
    {
      multiHandLandmarks: [createDorsumLandmarks()],
      multiHandedness: [{ label: "Right", score: 0.98 }],
    },
    1200,
    900
  );

  assert.equal(result.candidates.length, 5);
  assert.deepEqual(
    result.candidates.map((candidate) => candidate.suggestedFinger),
    [0, 1, 2, 3, 4]
  );
  assert.ok(result.candidates.every((candidate) => candidate.source === "mediapipe"));
  assert.ok(result.candidates.every((candidate) => candidate.confidence === "medium"));
  assert.deepEqual(result.warnings, ["model_unavailable_used_mediapipe_geometry"]);
});

test("hand geometry refuses a clear palm-facing image", () => {
  const landmarks = createDorsumLandmarks();
  [landmarks[5], landmarks[17]] = [landmarks[17], landmarks[5]];
  const result = createNailCandidatesFromHandGeometry(
    {
      multiHandLandmarks: [landmarks],
      multiHandedness: [{ label: "Right", score: 0.98 }],
    },
    1200,
    900
  );
  assert.equal(result.candidates.length, 0);
  assert.deepEqual(result.warnings, ["mediapipe_palm_facing"]);
});

test("hand geometry reports when no complete hand is present", () => {
  const result = createNailCandidatesFromHandGeometry({}, 1200, 900);
  assert.equal(result.candidates.length, 0);
  assert.deepEqual(result.warnings, ["mediapipe_no_hand_detected"]);
});
