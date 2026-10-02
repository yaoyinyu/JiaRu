import { spawnSync } from "node:child_process";
import assert from "node:assert/strict";
import test from "node:test";
test("配对标记诊断保留整组缺口、角色及已有低IoU候选", () => {
  const result = spawnSync("python", ["-X", "utf8", "tests/matched-marker-sensitivity-effects_test.py"], { encoding: "utf8" });
  assert.equal(result.status, 0, result.stdout + result.stderr);
  assert.match(result.stderr, /Ran 4 tests/);
});
