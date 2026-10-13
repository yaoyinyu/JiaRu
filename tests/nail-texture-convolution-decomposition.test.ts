import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import test from "node:test";

test("卷积解析保持独立数学参考、全域分块与冻结预算", () => {
  const result = spawnSync("python", ["-X", "utf8", "tests/native-convolution-decomposition_test.py"], {
    cwd: fileURLToPath(new URL("../", import.meta.url)), encoding: "utf8",
    env: { ...process.env, PYTHONIOENCODING: "utf-8", OPENBLAS_NUM_THREADS: "1", MKL_NUM_THREADS: "1", OMP_NUM_THREADS: "1" }, timeout: 120_000,
  });
  assert.equal(result.error, undefined, String(result.error));
  assert.equal(result.status, 0, `${result.stdout}\n${result.stderr}`);
  assert.match(result.stderr, /Ran 8 tests/);
});
