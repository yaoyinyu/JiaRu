import { spawnSync } from "node:child_process";
import assert from "node:assert/strict";
import test from "node:test";
test("标记探针原像素预测、逐甲迁移、角色与不可覆盖推理记录", () => {
  const result = spawnSync("python", ["-X", "utf8", "tests/train-role-marker-sensitivity-probe_test.py"], { encoding: "utf8" });
  assert.equal(result.status, 0, result.stdout + result.stderr);
  assert.match(result.stderr, /Ran 6 tests/);
});
