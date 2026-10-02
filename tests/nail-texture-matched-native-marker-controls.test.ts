import { execFileSync } from "node:child_process";
import assert from "node:assert/strict";
import test from "node:test";
test("匹配标记对照的目标框保真、移位对照与完整分母拒绝门", () => {
  const output = execFileSync("python", ["-X", "utf8", "tests/matched-native-marker-controls_test.py"], { encoding: "utf8", stdio: "pipe" });
  assert.equal(output, "");
});
