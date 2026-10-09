import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import test from "node:test";

test("训练准入合同拒绝无命中、缺证、跨实例迁移和未来模型循环", () => {
  const result = spawnSync("python", ["-X", "utf8", "tests/nail-training-admission-contract_test.py"], { encoding: "utf8" });
  assert.equal(result.status, 0, result.stdout + result.stderr);
});
