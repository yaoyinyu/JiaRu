import { spawnSync } from "node:child_process";
import assert from "node:assert/strict";
import test from "node:test";
test("旧控制闭合按完整组与实际裁决继承，缺新布尔字段不缩分母也不授训练许可", () => {
 const r=spawnSync("python",["-X","utf8","tests/training-admission-evidence-ledger-v2_test.py"],{encoding:"utf8"});
 assert.equal(r.status,0,r.stdout+r.stderr);assert.match(r.stderr,/Ran 3 tests/);
});
