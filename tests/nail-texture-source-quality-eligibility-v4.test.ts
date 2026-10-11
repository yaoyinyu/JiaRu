import { spawnSync } from "node:child_process";
import assert from "node:assert/strict";
import test from "node:test";

test("整图资格v4保留历史原像素证据并拒绝多页缺失或身份漂移", () => {
  const result = spawnSync("python", ["-X", "utf8", "tests/source-quality-eligibility-v4_test.py"], { encoding: "utf8" });
  assert.equal(result.status, 0, result.stdout + result.stderr);
  assert.match(result.stderr, /Ran 12 tests/);
});
