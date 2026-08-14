import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";

const script = path.resolve("model/training/build-candidate7-annotation-workspace.py");

test("candidate7 workspace builder rejects a missing review report", () => {
  const root = mkdtempSync(path.join(tmpdir(), "candidate7-workspace-"));
  const output = path.join(root, "workspace");
  const result = spawnSync("python", [script, "--source-review-report", path.join(root, "missing.json"), "--output-dir", output], { encoding: "utf8" });
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /missing source-review report/);
});

test("candidate7 workspace verifier rejects manifest drift before candidate generation", () => {
  const root = mkdtempSync(path.join(tmpdir(), "candidate7-workspace-verify-"));
  const manifestPath = path.join(root, "annotation-workspace-manifest.json");
  writeFileSync(manifestPath, JSON.stringify({ schemaVersion: 1, ok: true, decision: "candidate7_annotation_workspace_ready_candidate_only", trainingUse: "permitted" }));
  const result = spawnSync("python", [script, "--verify-workspace", manifestPath], { encoding: "utf8" });
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /must remain training prohibited/);
});

test("candidate7 prelabel consumers explicitly recognize the candidate-only workspace", () => {
  const generateSource = readFileSync(path.resolve("model/training/generate-yolo-prelabels.py"), "utf8");
  const auditSource = readFileSync(path.resolve("model/training/audit-real-material-yolo-prelabels.py"), "utf8");
  const promptSource = readFileSync(path.resolve("model/training/build-sam-prompts-from-annotation-workspace.py"), "utf8");
  const visualEvidenceSource = readFileSync(path.resolve("model/training/build-sam-annotation-visual-review-evidence.py"), "utf8");
  const maskReviewSource = readFileSync(path.resolve("model/training/build-first-annotation-mask-review-workspace.py"), "utf8");
  assert.match(generateSource, /candidate7_annotation_workspace_ready_candidate_only/);
  assert.match(auditSource, /candidate7_annotation_workspace_ready_candidate_only/);
  assert.match(promptSource, /candidate7_annotation_workspace_ready_candidate_only/);
  assert.match(visualEvidenceSource, /sam_candidate_only_not_training_truth/);
  assert.match(maskReviewSource, /candidate7_annotation_workspace_ready_candidate_only/);
  assert.match(auditSource, /requires_explicit_candidate_gates/);
});
