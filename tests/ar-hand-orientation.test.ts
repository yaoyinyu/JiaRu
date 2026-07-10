import assert from "node:assert/strict";
import test from "node:test";
import {
  classifyHandDepthOrientation,
  classifyHandOrientation,
  getHandOrientationPresentation,
  normalizePalmCrossForHandedness,
} from "../src/lib/ar-hand-orientation.ts";

test("palm detector state is presented as 手心", () => {
  assert.deepEqual(getHandOrientationPresentation("palm"), {
    label: "手心",
    icon: "✋",
    tone: "palm",
  });
});

test("dorsum detector state is presented as 手背", () => {
  assert.deepEqual(getHandOrientationPresentation("dorsum"), {
    label: "手背",
    icon: "🖐️",
    tone: "dorsum",
  });
});

test("positive depth evidence classifies an open palm", () => {
  const decision = classifyHandDepthOrientation(0.01, [0.006, 0.005, 0.004, 0.006]);
  assert.equal(decision.orientation, "palm");
  assert.equal(decision.render, false);
  assert.equal(decision.confidence, "high");
});

test("negative depth evidence classifies the back of a hand", () => {
  const decision = classifyHandDepthOrientation(-0.01, [-0.006, -0.005, -0.004, -0.006]);
  assert.equal(decision.orientation, "dorsum");
  assert.equal(decision.render, true);
  assert.equal(decision.confidence, "high");
});

test("weak or conflicting depth evidence remains ambiguous", () => {
  const weak = classifyHandDepthOrientation(0.001, [0.001, -0.001, 0, 0.002]);
  const conflicting = classifyHandDepthOrientation(0, [-0.005, -0.005, 0.005, 0.005]);
  assert.equal(weak.orientation, "ambiguous");
  assert.equal(conflicting.orientation, "ambiguous");
});

test("raw handedness normalizes palm topology before display mirroring", () => {
  assert.equal(normalizePalmCrossForHandedness(0.03, "Right"), 0.03);
  assert.equal(normalizePalmCrossForHandedness(-0.03, "Left"), 0.03);
  assert.equal(normalizePalmCrossForHandedness(0.03, null), 0);
});

test("strong palm topology blocks nails even when depth is weak", () => {
  const decision = classifyHandOrientation({
    palmDepthDiff: 0,
    fingerDepthDiffs: [0.001, -0.001, 0, 0.001],
    palmCrossZ: 0.025,
    handedness: "Right",
  });

  assert.equal(decision.orientation, "palm");
  assert.equal(decision.render, false);
  assert.equal(decision.confidence, "high");
});

test("strong dorsum topology renders nails despite misleading palm depth", () => {
  const decision = classifyHandOrientation({
    palmDepthDiff: 0.012,
    fingerDepthDiffs: [0.007, 0.006, 0.005, 0.006],
    palmCrossZ: -0.025,
    handedness: "Right",
  });

  assert.equal(decision.orientation, "dorsum");
  assert.equal(decision.render, true);
  assert.equal(decision.confidence, "high");
});

test("weak side topology still falls back to depth evidence", () => {
  const decision = classifyHandOrientation({
    palmDepthDiff: -0.01,
    fingerDepthDiffs: [-0.006, -0.005, -0.004, -0.006],
    palmCrossZ: -0.0005,
    handedness: "Right",
  });

  assert.equal(decision.orientation, "dorsum");
  assert.equal(decision.render, true);
});
