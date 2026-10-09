import { spawnSync } from "node:child_process";
import assert from "node:assert/strict";
import test from "node:test";
test("现行真值坐标对/字典/归一化保持像素，拒绝身份与分母漂移", () => {
  const result = spawnSync("python", ["-X", "utf8", "tests/current-nail-truth-masks_test.py"], { encoding: "utf8" });
  assert.equal(result.status, 0, result.stdout + result.stderr);
  assert.match(result.stderr, /Ran 4 tests/);
});
