import { spawnSync } from "node:child_process";
import assert from "node:assert/strict";
import test from "node:test";
test("固定ROI上下文扩展保持旧策略、完整真值和边界行为", () => {
  const result = spawnSync("python", ["-X", "utf8", "tests/saved-roi-context-policy_test.py"], { encoding: "utf8" });
  assert.equal(result.status, 0, result.stdout + result.stderr);
  assert.match(result.stderr, /Ran 5 tests/);
});
