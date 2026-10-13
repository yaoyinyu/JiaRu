import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import test from "node:test";

test("完整候选保持原图字节、四比例顺序及全部控制前置门", () => {
  const r = spawnSync("python", ["-X", "utf8", "tests/native-joint-fullmodel_test.py"], {
    cwd: fileURLToPath(new URL("../", import.meta.url)), encoding: "utf8",
    env: { ...process.env, PYTHONIOENCODING: "utf-8" }, timeout: 120_000,
  });
  assert.equal(r.error, undefined, String(r.error));
  assert.equal(r.status, 0, `${r.stdout}\n${r.stderr}`);
  assert.match(r.stderr, /Ran 8 tests/);
});
