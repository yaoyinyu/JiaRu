import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import test from "node:test";

const cwd = fileURLToPath(new URL("../", import.meta.url));

test("原生坐标图保留原权重和两头，拒绝新增输入类型与形状漂移", () => {
  const result = spawnSync("python", ["-X", "utf8", "tests/native-coordinate-graph_test.py"], {
    cwd, encoding: "utf8", env: { ...process.env, PYTHONIOENCODING: "utf-8" }, timeout: 120_000,
  });
  assert.equal(result.error, undefined, String(result.error));
  assert.equal(result.status, 0, `${result.stdout}\n${result.stderr}`);
  assert.match(result.stderr, /Ran 3 tests/);
});

test("浏览器原生坐标输入与新两头路由回归", () => {
  const childEnv = { ...process.env };
  delete childEnv.NODE_TEST_CONTEXT;
  const result = spawnSync(process.execPath, ["--test", "--test-concurrency=1", "tests/nail-native-coordinates.test.mjs"], {
    cwd, encoding: "utf8", env: childEnv, timeout: 120_000,
  });
  assert.equal(result.error, undefined, String(result.error));
  assert.equal(result.status, 0, `${result.stdout}\n${result.stderr}`);
  assert.match(result.stdout, /pass 3/);
});
