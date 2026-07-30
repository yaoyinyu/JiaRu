import assert from "node:assert/strict";
import test from "node:test";
import {
  adjustNailGeometry,
  computeNailGeometry,
  createNailAffineTransform,
  mapGeometryScale,
  NAIL_DIPS,
  NAIL_PIPS,
  NAIL_TIPS,
  type NailLandmark,
} from "../src/lib/nail-geometry.ts";

function perspectiveLandmarks({
  tipY = 0.25,
  tipZ = 0,
  indexMcpZ = 0,
  pinkyMcpZ = 0,
}: {
  tipY?: number;
  tipZ?: number;
  indexMcpZ?: number;
  pinkyMcpZ?: number;
} = {}): NailLandmark[] {
  const points = Array.from({ length: 21 }, () => ({ x: 0.5, y: 0.5, z: 0 }));
  points[0] = { x: 0.5, y: 0.78, z: 0 };
  points[5] = { x: 0.38, y: 0.58, z: indexMcpZ };
  points[9] = { x: 0.5, y: 0.54, z: 0 };
  points[17] = { x: 0.62, y: 0.58, z: pinkyMcpZ };
  points[NAIL_PIPS[2]] = { x: 0.5, y: 0.45, z: 0 };
  points[NAIL_DIPS[2]] = { x: 0.5, y: 0.35, z: 0 };
  points[NAIL_TIPS[2]] = { x: 0.5, y: tipY, z: tipZ };
  return points;
}

function landmarksForDirection(dx: number, dy: number): NailLandmark[] {
  const points = Array.from({ length: 21 }, () => ({ x: 0.5, y: 0.5, z: 0 }));
  points[NAIL_DIPS[2]] = { x: 0.5, y: 0.5, z: 0 };
  points[NAIL_TIPS[2]] = { x: 0.5 + dx, y: 0.5 + dy, z: 0 };
  return points;
}

function directionFromAngle(angle: number): { x: number; y: number } {
  return { x: Math.sin(angle), y: -Math.cos(angle) };
}

for (const [name, dx, dy] of [
  ["up", 0, -0.1],
  ["right", 0.1, 0],
  ["diagonal", 0.1, -0.1],
] as const) {
  test(`nail local -Y follows ${name} fingertip direction`, () => {
    const geometry = computeNailGeometry(landmarksForDirection(dx, dy), 2, 800, 600);
    assert.ok(geometry);
    const rendered = directionFromAngle(geometry.angle);
    const expectedLength = Math.hypot(dx * 800, dy * 600);
    const expected = { x: dx * 800 / expectedLength, y: dy * 600 / expectedLength };
    const dot = rendered.x * expected.x + rendered.y * expected.y;
    const errorDegrees = Math.acos(Math.min(1, Math.max(-1, dot))) * 180 / Math.PI;
    assert.ok(errorDegrees < 0.5, `direction error was ${errorDegrees}°`);
  });
}

test("normalized landmarks produce an in-bounds canvas candidate", () => {
  const geometry = computeNailGeometry(landmarksForDirection(0, -0.1), 2, 800, 600);
  assert.ok(geometry);
  assert.ok(geometry.cx >= 0 && geometry.cx <= 800);
  assert.ok(geometry.cy >= 0 && geometry.cy <= 600);
  assert.ok(geometry.length > 0 && geometry.length < 600);
  assert.ok(geometry.width > 0 && geometry.width < 800);
});

test("calibrated middle-finger geometry covers the distal nail surface", () => {
  const geometry = computeNailGeometry(landmarksForDirection(0, -0.1), 2, 800, 600);
  assert.ok(geometry);
  assert.ok(Math.abs(geometry.length - 44.4) < 0.001);
  assert.ok(Math.abs(geometry.width - 32.4) < 0.001);
  assert.ok(Math.abs(geometry.cy - 260.4) < 0.001);
});

test("fit adjustment scales around the center and moves toward the nail root", () => {
  const adjusted = adjustNailGeometry(
    { cx: 100, cy: 100, length: 40, width: 20, angle: 0 },
    1.25,
    0.1
  );
  assert.deepEqual(adjusted, {
    cx: 100,
    cy: 104,
    length: 50,
    width: 25,
    angle: 0,
  });
});

test("display geometry maps back to original pixels without drift", () => {
  const display = { cx: 240, cy: 180, length: 60, width: 36, angle: 0.7 };
  const original = mapGeometryScale(display, 2.5);
  assert.deepEqual(original, {
    cx: 600,
    cy: 450,
    length: 150,
    width: 90,
    angle: 0.7,
  });
});

test("depth-aware fit keeps nail width when the fingertip points toward the camera", () => {
  const geometry = computeNailGeometry(
    perspectiveLandmarks({ tipY: 0.31, tipZ: -0.05 }),
    2,
    800,
    600,
    { zScale: 800 },
  );
  assert.ok(geometry);
  const projectedOnlyWidth = Math.abs(0.31 - 0.35) * 600 * 0.54;
  assert.ok(
    geometry.width > projectedOnlyWidth * 1.7,
    `expected depth-aware width, got ${geometry.width}`,
  );
  assert.ok(geometry.length < geometry.width);
});

test("rolled hand produces a non-orthogonal transverse axis and narrower nail", () => {
  const frontal = computeNailGeometry(perspectiveLandmarks(), 2, 800, 600, { zScale: 800 });
  const rolled = computeNailGeometry(
    perspectiveLandmarks({ indexMcpZ: -0.08, pinkyMcpZ: 0.08 }),
    2,
    800,
    600,
    { zScale: 800 },
  );
  assert.ok(frontal && rolled);
  assert.ok(rolled.width < frontal.width * 0.9);
  assert.notEqual(rolled.transverseAngle, undefined);
  const orthogonalError = Math.abs(
    Math.cos((rolled.transverseAngle ?? rolled.angle) - rolled.angle),
  );
  assert.ok(orthogonalError > 0.02, `expected perspective shear, got ${orthogonalError}`);
});

test("affine transform keeps local nail tip aligned with the fingertip axis", () => {
  const geometry = computeNailGeometry(
    perspectiveLandmarks({ indexMcpZ: -0.08, pinkyMcpZ: 0.08 }),
    2,
    800,
    600,
    { zScale: 800 },
  );
  assert.ok(geometry);
  const matrix = createNailAffineTransform(geometry);
  const tipVector = { x: -matrix.c, y: -matrix.d };
  const expected = directionFromAngle(geometry.angle);
  assert.ok(Math.abs(tipVector.x - expected.x) < 1e-9);
  assert.ok(Math.abs(tipVector.y - expected.y) < 1e-9);
});

test("per-finger calibration adjusts length and width independently", () => {
  const adjusted = adjustNailGeometry(
    { cx: 100, cy: 100, length: 40, width: 20, angle: 0 },
    1.25,
    0,
    0.8,
  );
  assert.equal(adjusted.length, 50);
  assert.equal(adjusted.width, 16);
});
