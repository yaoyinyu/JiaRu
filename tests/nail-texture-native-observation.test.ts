import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import test from "node:test";

test("观测图保留完整原图字节，实际全分母控制通过前禁止学得诊断", () => {
  const result = spawnSync("python", ["-X", "utf8", "tests/reviewed-native-observation_test.py"], {
    cwd: fileURLToPath(new URL("../", import.meta.url)), encoding: "utf8",
    env: { ...process.env, PYTHONIOENCODING: "utf-8" }, timeout: 120_000,
  });
  assert.equal(result.error, undefined, String(result.error));
  assert.equal(result.status, 0, `${result.stdout}\n${result.stderr}`);
  assert.match(result.stderr, /Ran 7 tests/);
});
