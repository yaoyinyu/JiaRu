import { spawnSync } from "node:child_process";
import assert from "node:assert/strict";
import test from "node:test";

test("源质量投影v2验证完整旧分母、实看身份、新库存计数和运行器身份", () => {
  const result = spawnSync("python", ["-X", "utf8", "tests/source-quality-eligibility-v2_test.py"], { encoding: "utf8" });
  assert.equal(result.status, 0, result.stdout + result.stderr);
  assert.match(result.stderr, /Ran 6 tests/);
});
