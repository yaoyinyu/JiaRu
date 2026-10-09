import { spawnSync } from "node:child_process";
import assert from "node:assert/strict";
import test from "node:test";
test("完整原像素实审证据复用拒绝缺页、缩放、漂移及资格晋升", () => {
 const r = spawnSync("python", ["-X", "utf8", "tests/native-source-view-reuse_test.py"], { encoding: "utf8" });
 assert.equal(r.status, 0, r.stdout + r.stderr);
 assert.match(r.stderr, /Ran 4 tests/);
});
