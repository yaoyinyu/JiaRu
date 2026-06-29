import assert from "node:assert/strict";
import test from "node:test";
import {
  computeNailGeometry,
  mapGeometryScale,
  NAIL_DIPS,
  NAIL_TIPS,
  type NailLandmark,
} from "../src/lib/nail-geometry.ts";

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
