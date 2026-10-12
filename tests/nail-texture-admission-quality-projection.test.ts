import { spawnSync } from "node:child_process";
import assert from "node:assert/strict";
import test from "node:test";

test("训练准入质量投影验证原完整分母和被排除行，不隐藏真值漂移", () => {
  const result = spawnSync("python", ["-X", "utf8", "tests/training-admission-quality-projection_test.py"], { encoding: "utf8" });
  assert.equal(result.status, 0, result.stdout + result.stderr);
  assert.match(result.stderr, /Ran 5 tests/);
});
