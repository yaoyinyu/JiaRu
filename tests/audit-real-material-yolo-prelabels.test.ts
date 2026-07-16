import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { mkdirSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import test from "node:test";

const script = path.resolve("model/training/audit-real-material-yolo-prelabels.py");
const hash = (file: string) => createHash("sha256").update(readFileSync(file)).digest("hex");

test("YOLO prelabel audit reports count gaps without approving candidate truth", () => {
  const root = mkdtempSync(path.join(tmpdir(), "prelabel-audit-"));
  const annotationDir = path.join(root, "annotations");
  mkdirSync(annotationDir);
  const workspace = path.join(root, "workspace.json");
  writeFileSync(workspace, JSON.stringify({
    ok: true,
    decision: "annotation_workspace_ready_candidate_only",
    items: [{ fileName: "a.jpg", sha256: "a", sourceGroup: "g1", expectedFullyVisibleNails: 2 }],
  }));
  const annotation = path.join(annotationDir, "a.json");
  writeFileSync(annotation, JSON.stringify({
    decision: "candidate_only_not_training_truth",
    image: { fileName: "a.jpg", sourceGroup: "g1", width: 100, height: 100 },
    annotations: [{ polygon: [{ x: 10, y: 10 }, { x: 30, y: 10 }, { x: 30, y: 30 }, { x: 10, y: 30 }] }],
  }));
  const prelabel = path.join(root, "prelabel.json");
  writeFileSync(prelabel, JSON.stringify({
    ok: true,
    decision: "candidate_only_not_training_truth",
    workspaceManifestSha256: hash(workspace),
    items: [{ fileName: "a.jpg", sha256: "a", sourceGroup: "g1", candidateCount: 1, annotationPath: annotation }],
  }));
  const output = path.join(root, "output");
  const result = spawnSync("python", [script, "--workspace-manifest", workspace, "--prelabel-report", prelabel, "--output-dir", output], { encoding: "utf8" });
  assert.equal(result.status, 0, result.stderr);
  const report = JSON.parse(readFileSync(path.join(output, "prelabel-audit-report.json"), "utf8"));
  assert.equal(report.decision, "prelabel_candidate_audit_pass_original_resolution_review_required");
  assert.equal(report.counts.underCandidateImages, 1);
  assert.equal(report.counts.cappedCountCoverage, 0.5);
  assert.equal(report.policy.candidateAnnotationsAreNotTrainingTruth, true);
});

test("YOLO prelabel audit keeps overlapping candidates as visual suspects rather than approved truth", () => {
  const root = mkdtempSync(path.join(tmpdir(), "prelabel-overlap-"));
  const annotationDir = path.join(root, "annotations");
  mkdirSync(annotationDir);
  const workspace = path.join(root, "workspace.json");
  writeFileSync(workspace, JSON.stringify({ ok: true, decision: "annotation_workspace_ready_candidate_only", items: [{ fileName: "a.jpg", sha256: "a", sourceGroup: "g1", expectedFullyVisibleNails: 2 }] }));
  const polygon = [{ x: 10, y: 10 }, { x: 40, y: 10 }, { x: 40, y: 40 }, { x: 10, y: 40 }];
  const annotation = path.join(annotationDir, "a.json");
  writeFileSync(annotation, JSON.stringify({ decision: "candidate_only_not_training_truth", image: { fileName: "a.jpg", sourceGroup: "g1", width: 100, height: 100 }, annotations: [{ polygon }, { polygon }] }));
  const prelabel = path.join(root, "prelabel.json");
  writeFileSync(prelabel, JSON.stringify({ ok: true, decision: "candidate_only_not_training_truth", workspaceManifestSha256: hash(workspace), items: [{ fileName: "a.jpg", sha256: "a", sourceGroup: "g1", candidateCount: 2, annotationPath: annotation }] }));
  const output = path.join(root, "output");
  const result = spawnSync("python", [script, "--workspace-manifest", workspace, "--prelabel-report", prelabel, "--output-dir", output], { encoding: "utf8" });
  assert.equal(result.status, 0, result.stderr);
  const report = JSON.parse(readFileSync(path.join(output, "prelabel-audit-report.json"), "utf8"));
  assert.equal(report.counts.duplicateOverlapPairs, 1);
  assert.equal(report.counts.machineErrors, 0);
  assert.equal(report.policy.originalResolutionReviewRequired, true);
});
