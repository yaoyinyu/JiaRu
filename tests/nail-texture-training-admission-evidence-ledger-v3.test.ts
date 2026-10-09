import { spawnSync } from "node:child_process";
import assert from "node:assert/strict";
import test from "node:test";

test("完整旧ROI先验真值与身份，再按当前整组资格计算覆盖，不隐藏坏记录或回训", () => {
 const r=spawnSync("python",["-X","utf8","tests/training-admission-evidence-ledger-v3_test.py"],{encoding:"utf8"});
 assert.equal(r.status,0,r.stdout+r.stderr);assert.match(r.stderr,/Ran 5 tests/);
});
