import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import test from "node:test";

test("完整继承批在解码和写入前拒绝角色漂移与路径越界", () => {
  const r = spawnSync("python", ["-X", "utf8", "tests/inherited-native-pair-batch_test.py"], { encoding: "utf8" });
  assert.equal(r.status, 0, r.stdout + r.stderr);
  assert.match(r.stderr, /Ran 6 tests/);
});
