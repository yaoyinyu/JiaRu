import { spawnSync } from "node:child_process";
import assert from "node:assert/strict";
import test from "node:test";
test("准入证据按稳定角色身份复算，拒绝分母漂移且不从模糊描述推定循环", () => {
 const r=spawnSync("python",["-X","utf8","tests/training-admission-evidence-ledger_test.py"],{encoding:"utf8"});
 assert.equal(r.status,0,r.stdout+r.stderr);assert.match(r.stderr,/Ran 5 tests/);
});
