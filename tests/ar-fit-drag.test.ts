import test from "node:test";
import assert from "node:assert/strict";
import { dragNailFit, fitHandlePoints, mirroredCanvasPoint } from "../src/lib/ar-fit-drag.ts";
import { adjustNailGeometry } from "../src/lib/nail-geometry.ts";
import { computeTextureRenderPlan } from "../src/lib/ar-nail-shape.ts";
import { photographicLightGain } from "../src/lib/ar-texture-fit.ts";
import { needsArDirectionReview } from "../src/lib/ar-review-flow.ts";

const fit = { lengthScale: 1, widthScale: 1, rootOffset: 0, sideOffset: 0, rotationOffset: .2 };
const close = (a: number, b: number) => assert.ok(Math.abs(a - b) < 1e-8, `${a} vs ${b}`);

test("manual extraction still requests a preview when tip polarity is uncertain", () => {
  assert.equal(needsArDirectionReview(["normalization_tip_direction_unknown"]), true);
  assert.equal(needsArDirectionReview(["normalization_orientation_disagreement"]), true);
  assert.equal(needsArDirectionReview(undefined), false);
  assert.equal(needsArDirectionReview(["other_warning"]), false);
});

test("mirrored pointer mapping respects viewport offset and CSS/backing-store scaling", () => {
  assert.deepEqual(mirroredCanvasPoint(150, 75, { left: 100, top: 50, width: 200, height: 100 }, 800, 400), { x: 600, y: 100 });
});

for (const angle of [0, .7, 3.1, -2]) test(`drag root preserves length and width through shear/rotation at ${angle}`, () => {
  const raw = { cx: 150, cy: 200, length: 80, width: 40, angle, transverseAngle: angle + .25 };
  const render = adjustNailGeometry(raw, 1, 0, 1, 0, .2);
  const before = fitHandlePoints(render).root;
  const next = dragNailFit("root", 4, -3, raw, render, fit);
  const adjusted = adjustNailGeometry(raw, next.lengthScale, next.rootOffset, next.widthScale, next.sideOffset, next.rotationOffset);
  const after = fitHandlePoints(adjusted).root;
  close(after.x - before.x, 4); close(after.y - before.y, -3);
  close(adjusted.width, render.width); close(adjusted.length, render.length);
});

test("tip and side handles independently resize photographic nails around a fixed root", () => {
  const raw = { cx: 100, cy: 200, length: 50, width: 20, angle: .7, transverseAngle: 1 };
  const g = adjustNailGeometry(raw, 1, 0, 1, 0, .2);
  const rendered = { ...g, ...computeTextureRenderPlan(g, 4) };
  const tip = dragNailFit("tip", Math.sin(g.angle) * 8, -Math.cos(g.angle) * 8, raw, rendered, fit);
  const after = adjustNailGeometry(raw, tip.lengthScale, 0, 1, 0, .2);
  const plan = { ...after, ...computeTextureRenderPlan(after, 4, 3, tip.lengthScale, 1) };
  close(plan.length, rendered.length + 8);
  close(fitHandlePoints(plan).root.x, fitHandlePoints(rendered).root.x);
  close(fitHandlePoints(plan).root.y, fitHandlePoints(rendered).root.y);
  const side = dragNailFit("width", Math.cos(g.transverseAngle!) * 3, Math.sin(g.transverseAngle!) * 3, raw, rendered, fit);
  close(side.widthScale, 1.3); close(side.lengthScale, 1);
});

test("drag clamps calibration and rejects unstable shear or invalid motion", () => {
  const g = { cx: 0, cy: 0, width: 20, length: 50, angle: 0 };
  assert.equal(dragNailFit("tip", 0, -1000, g, g, fit).lengthScale, 1.4);
  assert.equal(dragNailFit("width", -1000, 0, g, g, fit).widthScale, .7);
  assert.equal(dragNailFit("root", 1000, 1000, g, g, fit).rootOffset, .2);
  assert.deepEqual(dragNailFit("root", NaN, 2, g, g, fit), fit);
  assert.deepEqual(dragNailFit("tip", 2, 2, g, { ...g, transverseAngle: Math.PI / 2 }, fit), fit);
});

test("photo lighting dims dark-camera overlays gently while leaving bright references unclipped", () => {
  assert.equal(photographicLightGain(NaN), 1);
  assert.equal(photographicLightGain(0), .65);
  assert.equal(photographicLightGain(1), 1);
  assert.ok(photographicLightGain(.2) < photographicLightGain(.5));
});
