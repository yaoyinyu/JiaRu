import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import test from "node:test";
test("来源相册增量拒绝旧目标重扫、缓存漂移、失败正控和保护角色变更",()=>{
 const result=spawnSync("python",["-X","utf8","tests/source-album-delta_test.py"],{encoding:"utf8"});
 assert.equal(result.status,0,result.stdout+result.stderr);
});
