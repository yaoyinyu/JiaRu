import assert from "node:assert/strict";
import test from "node:test";

import {
  NEU_TOGGLE_MAGNET_PULL_PX,
  NEU_TOGGLE_TRAVEL,
  resolveDragFrame,
} from "../src/lib/ui/toggle-drag.ts";

test("resolveDragFrame maps pointer drag to clamped knob position", () => {
  // 未选中起点 0：右拖 10px → 位置 10，未过中点
  const a = resolveDragFrame({ baseX: 0, startX: 100, x: 110 });
  assert.equal(a.x, 10);
  assert.equal(a.shouldCheck, false);
  assert.equal(a.moved, true);

  // 右拖超出右极：钳制到 travel
  const b = resolveDragFrame({ baseX: 0, startX: 100, x: 100 + NEU_TOGGLE_TRAVEL + 50 });
  assert.equal(b.x, NEU_TOGGLE_TRAVEL);
  assert.equal(b.shouldCheck, true);

  // 已选中起点 travel：左拖超出左极：钳制到 0
  const c = resolveDragFrame({ baseX: NEU_TOGGLE_TRAVEL, startX: 100, x: 40 });
  assert.equal(c.x, 0);
  assert.equal(c.shouldCheck, false);
});

test("resolveDragFrame applies magnetic pull past the midpoint toward the attracting pole", () => {
  const half = NEU_TOGGLE_TRAVEL / 2;

  // 未选中拖过中点：向右极倾斜 +pull
  const a = resolveDragFrame({ baseX: 0, startX: 100, x: 100 + Math.ceil(half) + 2 });
  assert.equal(a.shouldCheck, true);
  assert.equal(a.pull, NEU_TOGGLE_MAGNET_PULL_PX);

  // 已选中拖回中点以下：向左极倾斜 -pull
  const b = resolveDragFrame({ baseX: NEU_TOGGLE_TRAVEL, startX: 100, x: 100 - (half + 3) });
  assert.equal(b.shouldCheck, false);
  assert.equal(b.pull, -NEU_TOGGLE_MAGNET_PULL_PX);

  // 中点恰好持平：不倾斜、保持原状态（磁吸驻留）
  const c = resolveDragFrame({ baseX: 0, startX: 100, x: 100 + half });
  assert.equal(c.pull, 0);
  assert.equal(c.shouldCheck, false);
  const d = resolveDragFrame({ baseX: NEU_TOGGLE_TRAVEL, startX: 100, x: 100 + half - NEU_TOGGLE_TRAVEL });
  assert.equal(d.pull, 0);
  assert.equal(d.shouldCheck, false);

  // 接近右极时倾斜被钳制，x+pull 不越过 travel
  const e = resolveDragFrame({ baseX: 0, startX: 100, x: 100 + NEU_TOGGLE_TRAVEL - 2 });
  assert.equal(e.x, NEU_TOGGLE_TRAVEL - 2);
  assert.equal(e.pull, 2);
  assert.ok(e.x + e.pull <= NEU_TOGGLE_TRAVEL);
});

test("resolveDragFrame treats sub-threshold movement as a click", () => {
  const a = resolveDragFrame({ baseX: 0, startX: 100, x: 103 });
  assert.equal(a.moved, false);
  assert.equal(a.x, 3);

  const b = resolveDragFrame({ baseX: 0, startX: 100, x: 105 });
  assert.equal(b.moved, true);
});

test("resolveDragFrame flips exactly when crossing the midpoint from either side", () => {
  const travel = NEU_TOGGLE_TRAVEL;
  // 未选中：中点 +1 → 翻为选中
  assert.equal(resolveDragFrame({ baseX: 0, startX: 0, x: travel / 2 + 1 }).shouldCheck, true);
  // 未选中：中点 -1 → 保持未选
  assert.equal(resolveDragFrame({ baseX: 0, startX: 0, x: travel / 2 - 1 }).shouldCheck, false);
  // 已选中：回拖到中点 -1 → 翻为未选
  assert.equal(resolveDragFrame({ baseX: travel, startX: travel, x: travel / 2 - 1 }).shouldCheck, false);
  // 已选中：回拖到中点 +1 → 保持选中
  assert.equal(resolveDragFrame({ baseX: travel, startX: travel, x: travel / 2 + 1 }).shouldCheck, true);
});
