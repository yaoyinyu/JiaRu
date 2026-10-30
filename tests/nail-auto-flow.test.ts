import assert from "node:assert/strict";
import test from "node:test";

import {
  AUTO_FINGER_GUESS_WARNING,
  autoAssignNailRegionFingers,
} from "../src/lib/nail-auto-flow.ts";

interface Region {
  id: string;
  cx: number;
  assignedFinger: number | null;
  warnings?: string[];
}

function region(id: string, cx: number, assignedFinger: number | null): Region {
  return { id, cx, assignedFinger, warnings: [] };
}

test("autoAssignNailRegionFingers：已分配区域保持不变", () => {
  const input = [
    region("a", 100, 1),
    region("b", 200, 2),
  ];
  const result = autoAssignNailRegionFingers(input);
  assert.equal(result.guessedCount, 0);
  assert.deepEqual(result.assignments, []);
  assert.equal(result.regions[0].assignedFinger, 1);
  assert.equal(result.regions[1].assignedFinger, 2);
  assert.deepEqual(result.regions[0].warnings, []);
});

test("autoAssignNailRegionFingers：缺失指位按 x 序填入空闲指位并加推断告警", () => {
  const input = [
    region("a", 300, 2), // 已占用中指
    region("c", 500, null),
    region("b", 100, null),
  ];
  const result = autoAssignNailRegionFingers(input);
  assert.equal(result.guessedCount, 2);
  // 空闲指位 = [0,1,3,4]，按 cx 升序：b(100)→0，c(500)→1
  const byId = new Map(result.regions.map((item) => [item.id, item]));
  assert.equal(byId.get("b")?.assignedFinger, 0);
  assert.equal(byId.get("c")?.assignedFinger, 1);
  assert.ok(byId.get("b")?.warnings.includes(AUTO_FINGER_GUESS_WARNING));
  assert.ok(byId.get("c")?.warnings.includes(AUTO_FINGER_GUESS_WARNING));
  // 已分配区域不被改动、不加告警
  assert.equal(byId.get("a")?.assignedFinger, 2);
  assert.deepEqual(byId.get("a")?.warnings, []);
});

test("autoAssignNailRegionFingers：待分配数量超过空闲指位时多出部分留空", () => {
  const input = [
    region("a", 100, 3),
    region("b", 200, null),
    region("c", 300, null),
    region("d", 400, null),
    region("e", 500, null),
    region("f", 600, null),
  ];
  const result = autoAssignNailRegionFingers(input);
  // 空闲指位 = [0,1,2,4] 共 4 个，第 5 个待分配（f）保持 null
  assert.equal(result.guessedCount, 4);
  const byId = new Map(result.regions.map((item) => [item.id, item]));
  assert.equal(byId.get("f")?.assignedFinger, null);
  assert.equal(byId.get("f")?.warnings.includes(AUTO_FINGER_GUESS_WARNING), false);
});
