import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import test from "node:test";

test("原像素网格诊断拒绝失败正控、歧义、数值域漂移和无守卫解码", () => {
  const r = spawnSync("python", ["-X", "utf8", "tests/native-source-grid-diagnostic_test.py"], { encoding: "utf8" });
  assert.equal(r.status, 0, r.stdout + r.stderr);
  assert.match(r.stderr, /Ran 7 tests/);
});
