import { spawnSync } from "node:child_process";
import assert from "node:assert/strict";
import test from "node:test";
test("原像素来源复核拒绝缺页、错身份、缩放与自动晋升", () => {
 const r = spawnSync("python", ["-X", "utf8", "tests/native-source-review-pages_test.py"], { encoding: "utf8" });
 assert.equal(r.status, 0, r.stdout + r.stderr);
 assert.match(r.stderr, /Ran 4 tests/);
});
