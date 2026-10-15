import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import test from "node:test";

test("主机坐标直连保持完整图可逆并拒绝消费者与输入元数据漂移", () => {
  const run = spawnSync("python", ["-X", "utf8", "tests/native-coordinate-direct-graph_test.py"], {
    cwd: process.cwd(), encoding: "utf8", env: { ...process.env, PYTHONIOENCODING: "utf-8" },
  });
  assert.equal(run.status, 0, run.stdout + run.stderr);
  assert.match(run.stderr, /Ran 3 tests/);
});
