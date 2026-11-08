import assert from "node:assert/strict";
import test from "node:test";
import { measureTextureAlphaFrame, textureDrawRect, textureLayerSize, cuticleBlendDistance } from "../src/lib/ar-texture-fit.ts";
import { adjustNailGeometry, smoothNailGeometry, type NailGeometry } from "../src/lib/nail-geometry.ts";
import { computeTextureRenderPlan } from "../src/lib/ar-nail-shape.ts";
import { resolveMaskTextureRotation, WARNING_TIP_DIRECTION_UNKNOWN } from "../src/lib/nail-texture-recognition/mask-orientation.ts";

test("transparent padding does not change cuticle anchoring or nail-bed size", () => {
  for (const padding of [0, 2, 9]) {
    const width = 20 + padding * 2, height = 60 + padding * 2, rgba = new Uint8ClampedArray(width * height * 4);
    for (let y = padding; y < padding + 60; y++) for (let x = padding; x < padding + 20; x++) rgba[(y * width + x) * 4 + 3] = 255;
    const frame = measureTextureAlphaFrame(rgba, width, height), rect = textureDrawRect(frame, width, height, 30, 90);
    assert.equal(frame.bodyWidth, 20); assert.equal(frame.height, 60);
    assert.equal(rect.x + frame.rootX * rect.width / width, 0);
    assert.equal(rect.y + (frame.top + frame.height) * rect.height / height, 45);
    assert.equal(rect.width / width * frame.bodyWidth, 30);
  }
});

test("long photographic nails respond to length calibration while the root stays fixed", () => {
  const base = { cx: 80, cy: 100, length: 40, width: 20, angle: 0 };
  const plans = [.75, 1, 1.4].map(scale => computeTextureRenderPlan(adjustNailGeometry(base, scale, 0, 1), 4, 3, scale));
  assert.deepEqual(plans.map(p => p.length), [60, 80, 112]);
  for (const plan of plans) assert.equal(plan.cy + plan.length / 2, 120);
});

for (const flip of [false, true]) test(`tapered model mask recovers directed tip without trusting PCA: ${flip}`, () => {
  const width = 61, height = 101, data = new Uint8Array(width * height);
  for (let y = 5; y < 96; y++) {
    const along = flip ? 100 - y : y;
    const half = along < 60 ? Math.max(1, (along - 5) / 55 * 20) : 20;
    for (let x = 0; x < width; x++) if (Math.abs(x - 30) <= half) data[y * width + x] = 1;
  }
  const mask = { width, height, data, originX: 0, originY: 0, scale: 1 };
  const resolved = resolveMaskTextureRotation(mask, 0, false);
  assert.equal(resolved.source, "mask+taper");
  assert.ok(Math.cos(resolved.rotation) * (flip ? -1 : 1) > .99);
  const manual = resolveMaskTextureRotation(mask, flip ? 0 : Math.PI, true);
  assert.ok(Math.cos(manual.rotation) * (flip ? 1 : -1) > .99, "explicit manual reversal is respected");
});

test("a symmetric model mask keeps direction review visible", () => {
  const width = 25, height = 65, data = new Uint8Array(width * height);
  for (let y = 4; y < 61; y++) for (let x = 5; x < 20; x++) data[y * width + x] = 1;
  const result = resolveMaskTextureRotation({ width, height, data, originX: 0, originY: 0, scale: 1 }, 0, false);
  assert.ok(result.warnings.includes(WARNING_TIP_DIRECTION_UNKNOWN));
});

test("transparent tip or side survives even when most corners are opaque", () => {
  const width = 20, height = 60, rgba = new Uint8ClampedArray(width * height * 4).fill(255);
  assert.equal(measureTextureAlphaFrame(rgba, width, height).shaped, false);
  rgba[3] = 0;
  assert.equal(measureTextureAlphaFrame(rgba, width, height).shaped, true);
});

test("tip polarity follows rotated and mirrored tapered nails", () => {
  for (const angle of [0, .5, 1.3, Math.PI, -1, -2.5]) for (const mirrored of [false, true]) {
    const width = 141, height = 141, data = new Uint8Array(width * height);
    const tx = Math.sin(angle), ty = -Math.cos(angle);
    for (let y = 0; y < height; y++) for (let x = 0; x < width; x++) {
      const dx = (x - 70) * (mirrored ? -1 : 1), dy = y - 70;
      const along = dx * tx + dy * ty, cross = dx * -ty + dy * tx;
      const halfWidth = along > -10 ? Math.max(0, (45 - along) / 55 * 20) : 20;
      if (along >= -45 && along <= 45 && Math.abs(cross) <= halfWidth) data[y * width + x] = 1;
    }
    const r = resolveMaskTextureRotation({ width, height, data, originX: 0, originY: 0, scale: 1 }, 0, false);
    assert.equal(r.source, "mask+taper");
    assert.ok(Math.sin(r.rotation) * tx * (mirrored ? -1 : 1) - Math.cos(r.rotation) * ty > .98, `${angle}/${mirrored}`);
  }
});

test("tip decorations keep their size without shrinking the nail bed", () => {
  const width = 100, height = 160, rgba = new Uint8ClampedArray(width * height * 4);
  for (let y = 10; y < 150; y++) for (let x = 35; x < 65; x++) rgba[(y * width + x) * 4 + 3] = 255;
  for (let y = 30; y < 50; y++) for (let x = 5; x < 95; x++) rgba[(y * width + x) * 4 + 3] = 255;
  const frame = measureTextureAlphaFrame(rgba, width, height);
  assert.equal(frame.width, 90);
  assert.equal(frame.bodyWidth, 30);
  const rect = textureDrawRect(frame, width, height, 24, 112);
  assert.equal(rect.width / width * 30, 24);
  assert.equal(rect.width / width * 90, 72, "attached ornament remains visible at its relative size");
});

test("photographic length responds independently to longitudinal and transverse projection", () => {
  for (const angle of [0, .6, 2.4]) for (const longitudinal of [.4, .7, 1]) for (const transverse of [.3, .65, 1]) {
    const geometry = { cx: 90, cy: 120, angle, length: 40 * longitudinal, width: 20 * transverse,
      longitudinalProjection: longitudinal, transverseProjection: transverse };
    const plan = computeTextureRenderPlan(geometry, 4);
    assert.ok(Math.abs(plan.length - 80 * longitudinal) < 1e-8);
    assert.ok(Math.abs(plan.cx - Math.sin(angle) * plan.length / 2 - (geometry.cx - Math.sin(angle) * geometry.length / 2)) < 1e-8);
    assert.ok(Math.abs(plan.cy + Math.cos(angle) * plan.length / 2 - (geometry.cy + Math.cos(angle) * geometry.length / 2)) < 1e-8);
  }
});

test("width calibration leaves the selected photographic length unchanged", () => {
  const base = { cx: 90, cy: 120, angle: .5, length: 40, width: 20 };
  const plans = [.7, 1, 1.45].map(width => computeTextureRenderPlan(adjustNailGeometry(base, 1.2, 0, width), 4, 3, 1.2, width));
  for (const plan of plans) assert.ok(Math.abs(plan.length - 96) < 1e-8);
  assert.ok(plans.every(p => Math.abs(p.cx - plans[0].cx) < 1e-8 && Math.abs(p.cy - plans[0].cy) < 1e-8));
});

test("rotation and side calibration preserve the chosen root with perspective shear", () => {
  for (const angle of [0, .7, 2.8]) for (const rotation of [-.5, 0, .5]) {
    const base = { cx: 100, cy: 120, length: 40, width: 20, angle, transverseAngle: angle + .2,
      longitudinalProjection: .8, transverseProjection: .7 };
    const adjusted = adjustNailGeometry(base, 1.3, .1, .9, .3, rotation);
    const plan = computeTextureRenderPlan(adjusted, 4, 3, 1.3);
    const expectedX = base.cx - Math.sin(angle) * 24 + Math.cos(base.transverseAngle) * 6;
    const expectedY = base.cy + Math.cos(angle) * 24 + Math.sin(base.transverseAngle) * 6;
    assert.ok(Math.abs(plan.cx - Math.sin(adjusted.angle) * plan.length / 2 - expectedX) < 1e-8);
    assert.ok(Math.abs(plan.cy + Math.cos(adjusted.angle) * plan.length / 2 - expectedY) < 1e-8);
    assert.ok(Math.abs(Math.sin(adjusted.transverseAngle! - base.transverseAngle - rotation)) < 1e-8);
    assert.equal(adjusted.transverseProjection, .7);
  }
});

test("animated calibration preserves a stationary root across angle wrapping and length changes", () => {
  const root = { x: 160, y: 240 };
  const pose = (angle: number, length: number) => ({ cx: root.x + Math.sin(angle) * length / 2,
    cy: root.y - Math.cos(angle) * length / 2, angle, length, width: 20,
    longitudinalProjection: .7, transverseProjection: .6 });
  for (const pair of [[-.5, .5], [3.1, -3.1], [.4, 1.1]]) {
    let current: NailGeometry = pose(pair[0], 40);
    for (let frame = 0; frame < 15; frame++) {
      current = smoothNailGeometry(current, pose(pair[1], 90), .55);
      assert.ok(Math.abs(current.cx - Math.sin(current.angle) * current.length / 2 - root.x) < 1e-9);
      assert.ok(Math.abs(current.cy + Math.cos(current.angle) * current.length / 2 - root.y) < 1e-9);
      const rendered = computeTextureRenderPlan(current, 4);
      assert.ok(Math.abs(rendered.cx - Math.sin(current.angle) * rendered.length / 2 - root.x) < 1e-9);
      assert.ok(Math.abs(rendered.cy + Math.cos(current.angle) * rendered.length / 2 - root.y) < 1e-9);
    }
  }
});

test("smoothing moves the root monotonically and interpolates the two projection factors", () => {
  const previous = { cx: 0, cy: -20, angle: 0, length: 40, width: 20,
    longitudinalProjection: 1, transverseProjection: 1 };
  const current = { cx: 20, cy: -40, angle: 0, length: 80, width: 10,
    longitudinalProjection: .4, transverseProjection: .3 };
  const halfway = smoothNailGeometry(previous, current, .5);
  assert.equal(halfway.cx, 10); assert.equal(halfway.cy + halfway.length / 2, 0);
  assert.equal(halfway.longitudinalProjection, .7); assert.equal(halfway.transverseProjection, .65);
});

test("off-center wide decorations fit completely within the composition layer", () => {
  const frame = { left: 1, top: 4, width: 238, height: 50, bodyWidth: 8, rootX: 180, shaped: true };
  const rect = textureDrawRect(frame, 240, 60, 32, 80);
  const layer = textureLayerSize(rect, 32, 80);
  assert.ok(layer.width > 32 + 80 * .6 + 8, "generic padding would clip this ornament");
  assert.ok(rect.x >= -layer.width / 2 && rect.x + rect.width <= layer.width / 2);
  assert.ok(rect.y >= -layer.height / 2 && rect.y + rect.height <= layer.height / 2);
});

test("curved nail uses its cuticle center instead of the middle of the nail bed", () => {
  const width = 80, height = 100, rgba = new Uint8ClampedArray(width * height * 4);
  for (let y = 0; y < height; y++) {
    const center = y >= 82 ? 45 : 30;
    for (let x = center - 10; x < center + 10; x++) rgba[(y * width + x) * 4 + 3] = 255;
  }
  const frame = measureTextureAlphaFrame(rgba, width, height);
  assert.equal(frame.rootX, 45);
  assert.equal(frame.bodyWidth, 20);
  const rect = textureDrawRect(frame, width, height, 24, 100);
  assert.equal(rect.x + 45 * rect.width / width, 0);
});

test("cuticle blend stays short at small and large render sizes", () => {
  assert.equal(cuticleBlendDistance(10), .5);
  assert.equal(cuticleBlendDistance(40), 1);
  assert.equal(cuticleBlendDistance(200), 2);
});
