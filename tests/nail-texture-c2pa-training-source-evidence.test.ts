import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import test from "node:test";
test("C2PA局部签名成功、CLI退出零与空配料表不能替代完整来源或训练资格",()=>{
  const result=spawnSync("python",["-X","utf8","tests/c2pa-training-source-evidence_test.py"],{encoding:"utf8"});
  assert.equal(result.status,0,result.stdout+result.stderr);
});
