import { spawnSync } from "node:child_process";
import assert from "node:assert/strict";
import test from "node:test";

test("请求遥测未知保持未知，整图预算绑定及实测超限仍须拒绝", () => {
  const result = spawnSync("python", ["-X", "utf8", "tests/whole-source-quality-resource-window_test.py"], { encoding: "utf8" });
  assert.equal(result.status, 0, result.stdout + result.stderr);
  assert.match(result.stderr, /Ran 6 tests/);
});
