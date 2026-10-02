import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import test from "node:test";

test("容量执行日志通过预算拒重启与Windows共享锁回归", () => {
  for (const [filename, count] of [
    ["conditional-nail-bf16-execution_test.py", 2],
    ["conditional-nail-execution-journal_test.py", 3],
  ] as const) {
    const result = spawnSync("python", ["-X", "utf8", `tests/${filename}`], {
      cwd: fileURLToPath(new URL("../", import.meta.url)),
      encoding: "utf8",
      env: { ...process.env, PYTHONIOENCODING: "utf-8" },
      timeout: 120_000,
    });
    assert.equal(result.error, undefined, String(result.error));
    assert.equal(result.status, 0, `${result.stdout}\n${result.stderr}`);
    assert.match(result.stderr, new RegExp(`Ran ${count} tests`));
  }
});
