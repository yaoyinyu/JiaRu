import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import test from "node:test";
test("正控配准守住全幅/镜像/无候选与原误差门", () => {
  const r = spawnSync("python", ["-X", "utf8", "tests/native-source-registration-diagnostic_test.py"], { encoding: "utf8" });
  assert.equal(r.status, 0, r.stdout + r.stderr);
  assert.match(r.stderr, /Ran 5 tests/);
});
