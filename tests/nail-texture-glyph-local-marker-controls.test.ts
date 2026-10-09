import { spawnSync } from "node:child_process";
import assert from "node:assert/strict";
import test from "node:test";
test("局部字形控制保留原像素/相同支持形状及配对底图，拒绝重叠与空支持", () => {
  const result = spawnSync("python", ["-X", "utf8", "tests/glyph-local-marker-controls_test.py"], { encoding: "utf8" });
  assert.equal(result.status, 0, result.stdout + result.stderr);
  assert.match(result.stderr, /Ran 5 tests/);
});
