import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";

const script = path.resolve("model/training/build-candidate8-unseen-positive-workspace.py");

test("candidate8 workspace verifier rejects an unsafe training role", () => {
  const root = mkdtempSync(path.join(tmpdir(), "candidate8-workspace-verify-"));
  const manifestPath = path.join(root, "annotation-workspace-manifest.json");
  writeFileSync(manifestPath, JSON.stringify({
    schemaVersion: 1,
    ok: true,
    decision: "candidate8_annotation_workspace_ready_candidate_only",
    trainingUse: "permitted",
  }));
  const result = spawnSync("python", [script, "--verify-workspace", manifestPath], { encoding: "utf8" });
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /training prohibited/);
});

test("candidate8 prelabel generator explicitly recognizes its candidate-only workspace", () => {
  const source = readFileSync(path.resolve("model/training/generate-yolo-prelabels.py"), "utf8");
  assert.match(source, /candidate8_annotation_workspace_ready_candidate_only/);
});
