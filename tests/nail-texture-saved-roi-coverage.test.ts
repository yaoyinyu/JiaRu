import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import test from "node:test";

test("存档ROI一一覆盖上限、候选种子和原像素边界反例", () => {
  const result = spawnSync("python", ["-X", "utf8", "tests/saved-nail-roi-coverage_test.py"], { encoding: "utf8" });
  assert.equal(result.status, 0, result.stdout + result.stderr);
  assert.match(result.stderr, /Ran 8 tests/);
});
