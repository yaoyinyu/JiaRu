import { spawnSync } from "node:child_process";
import assert from "node:assert/strict";
import test from "node:test";

test("多来源存档ROI审计保留原图-only及多标记，并坚持一候选一甲和原分配", () => {
  const r = spawnSync("python", ["-X", "utf8", "tests/saved-multi-cohort-roi-prompt-reachability-v2_test.py"], { encoding: "utf8" });
  assert.equal(r.status, 0, r.stdout + r.stderr);
  assert.match(r.stderr, /Ran 10 tests/);
});
