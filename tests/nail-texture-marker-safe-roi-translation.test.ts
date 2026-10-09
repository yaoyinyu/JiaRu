import { spawnSync } from "node:child_process";
import assert from "node:assert/strict";
import test from "node:test";

test("ROI避标平移与整数穷举同构，保留尺寸/候选锚及完整基线失败门", () => {
  const result = spawnSync("python", ["-X", "utf8", "tests/marker-safe-roi-translation_test.py"], { encoding: "utf8" });
  assert.equal(result.status, 0, result.stdout + result.stderr);
  assert.match(result.stderr, /Ran 7 tests/);
});
