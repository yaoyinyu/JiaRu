import { spawnSync } from "node:child_process";
import assert from "node:assert/strict";
import test from "node:test";
test("来源父图召回保持冻结身份、分母和局部匹配门", () => {
 const r = spawnSync("python", ["-X", "utf8", "tests/source-parent-near-recall_test.py"], { encoding: "utf8" });
 assert.equal(r.status, 0, r.stdout + r.stderr);
 assert.match(r.stderr, /Ran 4 tests/);
});
