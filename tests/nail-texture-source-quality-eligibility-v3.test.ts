import { spawnSync } from "node:child_process";
import assert from "node:assert/strict";
import test from "node:test";

test("源质量资格v3拒绝缺页、重复页、缩放分块和原分母漂移", () => {
  const result = spawnSync("python", ["-X", "utf8", "tests/source-quality-eligibility-v3_test.py"], { encoding: "utf8" });
  assert.equal(result.status, 0, result.stdout + result.stderr);
  assert.match(result.stderr, /Ran 10 tests/);
});
