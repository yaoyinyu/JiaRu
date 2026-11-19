import assert from "node:assert/strict";
import test from "node:test";
import { smoothRadiusVector } from "../src/lib/nail-texture-recognition/radial-smoothing.ts";

const BINS = 2048;

function buildLattice(side = 96, center = 48): { bins: Int32Array; distance: Float32Array } {
  const bins = new Int32Array(side * side);
  const distance = new Float32Array(side * side);
  for (let y = 0; y < side; y += 1) {
    for (let x = 0; x < side; x += 1) {
      const offset = y * side + x;
      const dy = y - center + 0.5;
      const dx = x - center + 0.5;
      distance[offset] = Math.fround(Math.hypot(dy, dx));
      const theta = Math.atan2(dy, dx);
      bins[offset] = Math.min(BINS - 1, Math.floor(((theta + Math.PI) / (2 * Math.PI)) * BINS));
    }
  }
  return { bins, distance };
}

function decodedArea(radius: Float32Array, bins: Int32Array, distance: Float32Array): number {
  let area = 0;
  for (let index = 0; index < distance.length; index += 1) {
    if (Math.fround(Math.fround(radius[bins[index]]) - distance[index]) >= 0) area += 1;
  }
  return area;
}

function wobblyRadius(base = 40, amplitude = 3): Float32Array {
  const radius = new Float32Array(BINS);
  for (let index = 0; index < BINS; index += 1) {
    const low = base + 4 * Math.cos((2 * Math.PI * index) / BINS);
    const high = amplitude * Math.sin((2 * Math.PI * index * 37) / BINS);
    radius[index] = Math.fround(low + high);
  }
  return radius;
}

test("mode none returns the original vector untouched", () => {
  const { bins, distance } = buildLattice();
  const radius = wobblyRadius();
  const result = smoothRadiusVector(radius, bins, distance, { mode: "none" });
  assert.equal(result.applied, false);
  assert.equal(result.radius, radius);
  assert.equal(result.sigmaArcPixels, 0);
  assert.equal(result.areaCompensationPixels, 0);
});

test("shape mismatch is rejected instead of silently decoding", () => {
  const { bins } = buildLattice();
  const radius = wobblyRadius();
  const result = smoothRadiusVector(radius, bins, new Float32Array(3), { mode: "rms-bounded-gaussian" });
  assert.equal(result.applied, false);
});

test("a constant radius is invariant under smoothing and compensation", () => {
  const { bins, distance } = buildLattice();
  const radius = new Float32Array(BINS).fill(40);
  const result = smoothRadiusVector(radius, bins, distance, {
    mode: "rms-bounded-gaussian",
    deviationRmsArcPixels: 0.7,
    gridArcPixels: [0.5, 1, 2, 4],
    areaCompensation: true,
  });
  assert.equal(result.applied, true);
  for (const value of result.radius) assert.ok(Math.abs(value - 40) < 1e-4, `constant radius drifted to ${value}`);
  assert.ok(Math.abs(result.areaCompensationPixels) < 1e-3);
});

test("the chosen kernel respects the RMS bound and grows with the tolerance", () => {
  const { bins, distance } = buildLattice();
  const radius = wobblyRadius(40, 3);
  const grid = [0.5, 1, 1.5, 2, 2.5, 3, 4, 5, 6, 8];
  let previous = -1;
  for (const tolerance of [0.1, 0.3, 0.6, 1.2]) {
    const result = smoothRadiusVector(radius, bins, distance, {
      mode: "rms-bounded-gaussian",
      deviationRmsArcPixels: tolerance,
      gridArcPixels: grid,
      areaCompensation: false,
    });
    if (!result.applied) continue;
    const delta = Array.from(result.radius, (value, index) => value - radius[index]);
    const rms = Math.sqrt(delta.reduce((total, value) => total + value * value, 0) / delta.length);
    assert.ok(rms <= tolerance + 1e-4, `rms ${rms} exceeded tolerance ${tolerance}`);
    assert.ok(result.sigmaArcPixels >= previous, "sigma must not shrink when the tolerance grows");
    previous = result.sigmaArcPixels;
  }
});

test("area compensation keeps the decoded area within half a percent", () => {
  const { bins, distance } = buildLattice();
  const radius = wobblyRadius(40, 3);
  const before = decodedArea(radius, bins, distance);
  const result = smoothRadiusVector(radius, bins, distance, {
    mode: "rms-bounded-gaussian",
    deviationRmsArcPixels: 1.2,
    gridArcPixels: [0.5, 1, 2, 4, 6],
    areaCompensation: true,
  });
  assert.equal(result.applied, true);
  const after = decodedArea(result.radius, bins, distance);
  const relative = Math.abs(after - before) / before;
  assert.ok(relative <= 0.005, `area drift ${(relative * 100).toFixed(3)}% exceeds 0.5%`);
  assert.ok(Math.abs(result.areaCompensationPixels) <= 2);
});

test("without compensation the smoothing shrinks the area, which is what the flag exists for", () => {
  const { bins, distance } = buildLattice();
  const radius = wobblyRadius(40, 3);
  const before = decodedArea(radius, bins, distance);
  const result = smoothRadiusVector(radius, bins, distance, {
    mode: "rms-bounded-gaussian",
    deviationRmsArcPixels: 1.2,
    gridArcPixels: [0.5, 1, 2, 4, 6],
    areaCompensation: false,
  });
  assert.equal(result.applied, true);
  assert.equal(result.areaCompensationPixels, 0);
  const after = decodedArea(result.radius, bins, distance);
  assert.ok(after <= before, "uncompensated smoothing must not grow the mask");
});

test("smoothing is circular: a symmetric input stays symmetric across the bin seam", () => {
  const { bins, distance } = buildLattice();
  const radius = new Float32Array(BINS).fill(40);
  radius[0] = 44;
  const result = smoothRadiusVector(radius, bins, distance, {
    mode: "rms-bounded-gaussian",
    deviationRmsArcPixels: 1.5,
    gridArcPixels: [1, 2, 3],
    areaCompensation: false,
  });
  assert.equal(result.applied, true);
  assert.ok(Math.abs(result.radius[1] - result.radius[BINS - 1]) < 1e-5, "neighbours across the seam must match");
  assert.ok(result.radius[0] < 44, "the spike must be attenuated");
  assert.ok(result.radius[1] > 40, "the spike must spread to neighbours");
});
