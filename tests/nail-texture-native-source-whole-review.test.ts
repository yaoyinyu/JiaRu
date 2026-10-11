import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import test from "node:test";
test("完整源图与旧分块守住RGB、全覆盖、坐标及解码守卫", () => {
  const r = spawnSync("python", ["-X", "utf8", "tests/native-source-whole-review_test.py"], { encoding: "utf8" });
  assert.equal(r.status, 0, r.stdout + r.stderr);
  assert.match(r.stderr, /Ran 6 tests/);
});
