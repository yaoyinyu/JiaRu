import { spawnSync } from "node:child_process";
import assert from "node:assert/strict";
import test from "node:test";

test("源质量资格投影拒绝隐藏坏记录、缩放审核和颠倒覆盖缺口，并保持训练禁止", () => {
  const result = spawnSync("python", ["-X", "utf8", "tests/source-quality-eligibility.test.py"], { encoding: "utf8" });
  assert.equal(result.status, 0, result.stdout + result.stderr);
  assert.match(result.stderr, /Ran 4 tests/);
});
