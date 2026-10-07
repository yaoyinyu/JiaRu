import { spawnSync } from "node:child_process";
import assert from "node:assert/strict";
import test from "node:test";

test("内部val整组标记诊断保留角色、禁止回训、分母和逐甲迁移", () => {
  const result = spawnSync("python", ["-X", "utf8", "tests/internal-val-marker-sensitivity-probe_test.py"], { encoding: "utf8" });
  assert.equal(result.status, 0, result.stdout + result.stderr);
  assert.match(result.stderr, /Ran 8 tests/);
});
