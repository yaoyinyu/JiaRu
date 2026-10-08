import { spawnSync } from "node:child_process";
import assert from "node:assert/strict";
import test from "node:test";

test("异构train诊断保留全原图分母与质量排除，拒绝保护血缘和伪造控制通过", () => {
  const result = spawnSync("python", ["-X", "utf8", "tests/heterogeneous-quality-accounted-train-marker-probe_test.py"], { encoding: "utf8" });
  assert.equal(result.status, 0, result.stdout + result.stderr);
  assert.match(result.stderr, /Ran 9 tests/);
});
