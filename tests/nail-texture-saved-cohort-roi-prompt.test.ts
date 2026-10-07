import { spawnSync } from "node:child_process";
import assert from "node:assert/strict";
import test from "node:test";
test("存档整批ROI/提示审计硬保真、单候选一真值及完整分母", () => {
  const result = spawnSync("python", ["-X", "utf8", "tests/saved-cohort-roi-prompt-reachability_test.py"], { encoding: "utf8" });
  assert.equal(result.status, 0, result.stdout + result.stderr);
  assert.match(result.stderr, /Ran 7 tests/);
});
