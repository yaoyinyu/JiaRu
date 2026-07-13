import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { test } from "node:test";

const script = "model/training/build-consensus-nail-candidates.py";

test("cross-resolution consensus tool exposes guarded review-only CLI", () => {
  const result = spawnSync("python", [script, "--help"], { encoding: "utf8" });
  assert.equal(result.status, 0, result.stderr);
  assert.match(result.stdout, /--primary-annotations/);
  assert.match(result.stdout, /--secondary-annotations/);
  assert.match(result.stdout, /--minimum-iou/);
  assert.match(result.stdout, /review-only nail candidates/i);
});

test("cross-resolution consensus source keeps automatic output out of training truth", async () => {
  const source = await import("node:fs/promises").then((fs) => fs.readFile(script, "utf8"));
  assert.match(source, /candidate_only_not_training_truth/);
  assert.match(source, /cross-resolution-consensus-v1/);
  assert.match(source, /reviewRequired/);
});
