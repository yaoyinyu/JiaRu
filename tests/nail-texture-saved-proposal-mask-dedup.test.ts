import { spawnSync } from "node:child_process";
import assert from "node:assert/strict";
import test from "node:test";

test("固定mask重复规则前移的完整性替换和候选上限", () => {
  const result = spawnSync("python", ["-X", "utf8", "tests/saved-proposal-mask-dedup_test.py"], { encoding: "utf8" });
  assert.equal(result.status, 0, result.stdout + result.stderr);
  assert.match(result.stderr, /Ran 4 tests/);
});
