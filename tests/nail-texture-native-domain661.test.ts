import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import test from "node:test";

test("661部署域同时覆盖坐标、调度、内存与旧版本拒绝行为", () => {
  const env = { ...process.env };
  delete env.NODE_TEST_CONTEXT;
  const run = spawnSync(process.execPath, ["--test", "--test-concurrency=1",
    "tests/nail-native-coordinates.test.mjs", "tests/nail-native-coordinates-v2.test.mjs",
    "tests/nail-mask-f64-schedule.test.mjs", "tests/nail-mask-f64-schedule-v3.test.mjs"], {
    cwd: fileURLToPath(new URL("../", import.meta.url)), encoding: "utf8", env, timeout: 120_000,
  });
  assert.equal(run.error, undefined, String(run.error));
  assert.equal(run.status, 0, `${run.stdout}\n${run.stderr}`);
  assert.match(run.stdout, /tests 12/);
  assert.match(run.stdout, /pass 12/);
  assert.match(run.stdout, /fail 0/);
});
