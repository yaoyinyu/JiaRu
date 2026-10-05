import { spawnSync } from "node:child_process";
import assert from "node:assert/strict";
import test from "node:test";

test("可变标记诊断完整来源组、稳定身份、保护角色及逐变体分母", () => {
  const result = spawnSync("python", ["-X", "utf8", "tests/variable-train-role-marker-probe_test.py"], { encoding: "utf8" });
  assert.equal(result.status, 0, result.stdout + result.stderr);
  assert.match(result.stderr, /Ran 9 tests/);
});
