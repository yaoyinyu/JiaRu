import { spawnSync } from "node:child_process";
import assert from "node:assert/strict";
import test from "node:test";

test("存档条件输入的候选预算、同候选提示与标记相交反例", () => {
  const result = spawnSync("python", ["-X", "utf8", "tests/saved-conditional-input-preflight_test.py"], { encoding: "utf8" });
  assert.equal(result.status, 0, result.stdout + result.stderr);
  assert.match(result.stderr, /Ran 8 tests/);
});
