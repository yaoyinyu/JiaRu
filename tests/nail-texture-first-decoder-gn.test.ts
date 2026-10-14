import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import test from "node:test";

test("首GN分阶段执行保持全分母、FP64参考和禁止重启", () => {
  const result = spawnSync("python", ["-X", "utf8", "tests/native-first-decoder-gn_test.py"], {
    cwd: fileURLToPath(new URL("../", import.meta.url)), encoding: "utf8",
    env: { ...process.env, PYTHONIOENCODING: "utf-8" }, timeout: 120_000,
  });
  assert.equal(result.error, undefined, String(result.error));
  assert.equal(result.status, 0, `${result.stdout}\n${result.stderr}`);
  assert.match(result.stderr, /Ran 9 tests/);
});
