import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import test from "node:test";
test("相册增量队列保留双向角色与无命中，拒绝漏目标/未结束召回",()=>{
 const result=spawnSync("python",["-X","utf8","tests/source-album-native-pair-queue_test.py"],{encoding:"utf8"});
 assert.equal(result.status,0,result.stdout+result.stderr);
});
