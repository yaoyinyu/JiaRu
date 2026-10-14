import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import test from "node:test";

test("完整双域数学合同保持分母、原门与同坐标误差", () => {
  const result = spawnSync("python", ["-X", "utf8", "tests/reviewed-decoder-counterfactual_test.py"], {
    cwd: fileURLToPath(new URL("../", import.meta.url)), encoding: "utf8",
    env: { ...process.env, PYTHONIOENCODING: "utf-8", OPENBLAS_NUM_THREADS: "1", MKL_NUM_THREADS: "1", OMP_NUM_THREADS: "1" }, timeout: 120_000,
  });
  assert.equal(result.error, undefined, String(result.error));
  assert.equal(result.status, 0, `${result.stdout}\n${result.stderr}`);
  assert.match(result.stderr, /Ran 5 tests/);
});
