import { spawnSync } from "node:child_process";
import assert from "node:assert/strict";
import test from "node:test";
test("train整组诊断显式保留质量排除，拒绝保护角色与漏算成员", () => {
  const result = spawnSync("python", ["-X", "utf8", "tests/quality-accounted-train-marker-probe_test.py"], { encoding: "utf8" });
  assert.equal(result.status, 0, result.stdout + result.stderr);
  assert.match(result.stderr, /Ran 8 tests/);
});
