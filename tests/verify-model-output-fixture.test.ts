import assert from "node:assert/strict";
import { execFile } from "node:child_process";
import path from "node:path";
import { promisify } from "node:util";
import test from "node:test";

const execFileAsync = promisify(execFile);

test("verify-model-output-fixture validates offline postprocess assumptions", async () => {
  const fixturePath = path.resolve(
    "model/fixtures/nail-texture-model-output-sample.json"
  );

  const { stdout } = await execFileAsync(process.execPath, [
    "--no-warnings",
    "--experimental-strip-types",
    "scripts/verify-model-output-fixture.ts",
    fixturePath,
  ], {
    cwd: path.resolve("."),
  });

  const summary = JSON.parse(stdout) as {
    ok: boolean;
    candidateCount: number;
    failures: string[];
    candidates: Array<{
      suggestedFinger: number | null;
      hasMask: boolean;
    }>;
    debugOutputs: Array<{
      name: string;
      dims: number[];
    }>;
  };

  assert.equal(summary.ok, true);
  assert.equal(summary.candidateCount, 2);
  assert.deepEqual(summary.failures, []);
  assert.equal(summary.candidates[0].suggestedFinger, 1);
  assert.equal(summary.candidates[0].hasMask, true);
  assert.equal(summary.candidates[1].hasMask, true);
  assert.deepEqual(
    summary.debugOutputs.map((item) => item.name).sort(),
    ["boxes", "proto"]
  );
});
