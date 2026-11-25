import assert from "node:assert/strict";
import test from "node:test";
import {
  assignSegSlots,
  instanceMatchesTip,
  shouldScheduleKeyframe,
  updateSegHits,
} from "../src/lib/ar-seg-keyframe.ts";

const inst = (cx: number, cy: number, w = 0.05, h = 0.08, score = 0.8) => ({ cx, cy, w, h, angle: 0, score });

test("实例中心在指尖半径内命中", () => {
  assert.equal(instanceMatchesTip(inst(0.5, 0.5), { x: 0.52, y: 0.5 }, 0.06), true);
  assert.equal(instanceMatchesTip(inst(0.9, 0.9), { x: 0.5, y: 0.5 }, 0.06), false);
});

test("指尖落在实例外扩盒内命中（中心距超半径但盒覆盖）", () => {
  assert.equal(instanceMatchesTip(inst(0.5, 0.5, 0.2, 0.2), { x: 0.58, y: 0.5 }, 0.02), true);
});

test("关键帧调度：间隔不足或在途时不调度", () => {
  assert.equal(shouldScheduleKeyframe(1000, 0, 400, false), true);
  assert.equal(shouldScheduleKeyframe(300, 0, 400, false), false);
  assert.equal(shouldScheduleKeyframe(1000, 0, 400, true), false);
});

test("命中置 hit 并重置滞回；未命中递减保持后清除", () => {
  const tips = { 1: { x: 0.5, y: 0.5 } };
  let hits = updateSegHits({}, tips, [inst(0.5, 0.5)], 0.06, 3);
  assert.equal(hits[1].hit, true);
  assert.equal(hits[1].streak, 3);
  hits = updateSegHits(hits, tips, [], 0.06, 3);
  assert.equal(hits[1].hit, true);
  assert.equal(hits[1].streak, 2);
  hits = updateSegHits(hits, tips, [], 0.06, 3);
  hits = updateSegHits(hits, tips, [], 0.06, 3);
  assert.equal(hits[1].hit, false);
  assert.equal(hits[1].streak, 0);
});

test("兜底槽位按水平位置左→右分配并剔除低分", () => {
  const assigned = assignSegSlots([
    inst(0.7, 0.5, 0.05, 0.08, 0.8),
    inst(0.3, 0.5, 0.05, 0.08, 0.9),
    inst(0.5, 0.5, 0.05, 0.08, 0.1),
  ]);
  assert.deepEqual(assigned.map(a => a.slot), [0, 1]);
  assert.equal(assigned[0].instance.cx, 0.3);
  assert.equal(assigned[1].instance.cx, 0.7);
});

test("无关键点手指不产生条目", () => {
  const hits = updateSegHits({}, {}, [inst(0.5, 0.5)], 0.06, 3);
  assert.deepEqual(hits, {});
});