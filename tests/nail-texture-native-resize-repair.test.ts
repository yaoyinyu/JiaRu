import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import test from "node:test";

for (const [script, count] of [
  ["native-bilinear-resize_test.py", 4],
  ["native-resize-repair-contract_test.py", 3],
  ["trained-native-browser-contract_test.py", 6],
] as const) {
  test(`原尺寸插值表达与冻结修复合同：${script}`, () => {
    const result = spawnSync("python", ["-X", "utf8", `tests/${script}`], {
      cwd: fileURLToPath(new URL("../", import.meta.url)), encoding: "utf8",
      env: { ...process.env, PYTHONIOENCODING: "utf-8" }, timeout: 120_000,
    });
    assert.equal(result.error, undefined, String(result.error));
    assert.equal(result.status, 0, `${result.stdout}\n${result.stderr}`);
    assert.match(result.stderr, new RegExp(`Ran ${count} tests`));
  });
}
