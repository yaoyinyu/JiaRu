import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";

const script = path.resolve("model/training/audit-development-cycle-015-annotation-acceleration.py");

test("cycle015 annotation acceleration audit proves the scoped manual-work reduction", () => {
  const root = mkdtempSync(path.join(tmpdir(), "cycle015-annotation-acceleration-"));
  const write = (name: string, value: unknown) => {
    const file = path.join(root, name);
    writeFileSync(file, `${JSON.stringify(value)}\n`);
    return file;
  };
  const yolo = write("yolo.json", { ok: true, decision: "all_45_yolo_masks_rejected_for_boundary_rework", review: { reviewedNails: 45, accepted: 0, rework: 45 } });
  const sam = write("sam.json", { ok: true, imageCount: 9, promptCount: 45, boxOnlyFallbackPromptCount: 0, errors: [], outputs: Array.from({ length: 9 }, () => ({ polygonCount: 5 })) });
  const samGeometry = write("sam-geometry.json", { summary: { "cycle015-nine-image-sam21l-pca-multipoint-v1": { pass: 45, suspect: 0, missing: 0 } } });
  const samVisual = write("sam-visual.json", { ok: true, review: { accepted: 44, rework: 1 } });
  const residual = write("residual.json", { ok: true, imageCount: 1, polygonCount: 5, manualPolygonCount: 1, pairwiseOverlapCount: 0 });
  const finalCandidate = write("final-candidate.json", { ok: true, imageCount: 13, polygonCount: 85, pairwiseOverlapCount: 0 });
  const finalGeometry = write("final-geometry.json", { summary: { "cycle015-final-candidate-v1": { pass: 85, suspect: 0, missing: 0 } } });
  const maskReview = write("mask-review.json", { ok: true, counts: { images: 13, exclude: 0, pass: 13, rework: 0 } });
  const truth = write("truth.json", { ok: true, decision: "approved_unique_development_evaluation_truth_index", inputs: { truthRole: "development-evaluation" }, policy: { trainingUse: "prohibited" }, summary: { uniqueImageCount: 13, completeMaskCount: 85, conflictingImageCount: 0 } });
  const role = write("role.json", { ok: true, items: Array.from({ length: 13 }, (_, index) => ({ fileName: `${index}.png`, assignedRole: "development-evaluation-extension", trainingUse: "prohibited" })) });
  const invalidation = write("invalidation.json", { decision: "invalidated_role_mismatch_evidence_preserved", policy: { artifactsMustNotBeUsedForTraining: true } });
  const output = path.join(root, "report.json");
  const args = [
    script,
    "--yolo-visual-decision", yolo,
    "--sam-report", sam,
    "--sam-geometry", samGeometry,
    "--sam-visual-decision", samVisual,
    "--residual-manual-report", residual,
    "--final-candidate-report", finalCandidate,
    "--final-geometry", finalGeometry,
    "--mask-review-final", maskReview,
    "--development-truth-index", truth,
    "--role-manifest", role,
    "--invalidated-train-attempt", invalidation,
    "--output", output,
  ];
  const run = spawnSync("python", args, { encoding: "utf8" });
  assert.equal(run.status, 0, run.stderr || run.stdout);
  const report = JSON.parse(readFileSync(output, "utf8"));
  assert.equal(report.decision, "adopt_pca_multipoint_sam_for_exact_count_candidates_residual_manual_only");
  assert.equal(report.metrics.pcaMultipointSamAccepted, 44);
  assert.equal(report.metrics.residualManualNails, 1);
  assert.equal(report.metrics.manualBoundaryInterventionReductionRate, 44 / 45);
  assert.equal(report.policy.developmentEvaluationTrainingUse, "prohibited");

  const replay = spawnSync("python", [script, "--verify-report", output], { encoding: "utf8" });
  assert.equal(replay.status, 0, replay.stderr || replay.stdout);

  const changedRole = JSON.parse(readFileSync(role, "utf8"));
  changedRole.items[0].assignedRole = "train";
  writeFileSync(role, `${JSON.stringify(changedRole)}\n`);
  const rejected = spawnSync("python", args, { encoding: "utf8" });
  assert.notEqual(rejected.status, 0);
  assert.match(readFileSync(output, "utf8"), /frozen development-evaluation role manifest mismatch/);
});
