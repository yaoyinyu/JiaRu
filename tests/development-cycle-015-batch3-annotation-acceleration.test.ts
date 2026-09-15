import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";

const script = path.resolve("model/training/audit-development-cycle-015-batch3-annotation-acceleration.py");

function runAudit(trainingUse = "prohibited") {
  const root = mkdtempSync(path.join(tmpdir(), "cycle015-batch3-audit-"));
  const write = (name: string, value: unknown) => {
    const target = path.join(root, name);
    writeFileSync(target, typeof value === "string" ? value : JSON.stringify(value));
    return target;
  };
  const workspace = write("workspace.json", { ok: true, counts: { images: 10, expectedFullyVisibleNails: 60 }, items: Array.from({ length: 10 }, () => ({ assignedRole: "development-evaluation-extension", trainingUse })) });
  const prelabel = write("prelabel.json", { ok: true, counts: { images: 10, expectedFullyVisibleNails: 60, candidates: 60, cappedCountCoverage: 0.933333, zeroCandidateImages: 0, underCandidateImages: 1, exactCandidateImages: 7, overCandidateImages: 2, duplicateOverlapPairs: 2, machineErrors: 0 } });
  const prompts = write("prompts.json", { imageCount: 10, promptCount: 60, trimmedOverpredictionCandidateCount: 4, manualPromptRecoveryCount: 5, policy: { trainingUse: "prohibited" } });
  const sam = write("sam.json", { ok: true, promptCount: 60, errors: [], outputs: [{ polygonCount: 60 }] });
  const visual = write("visual.json", { ok: true, decision: "sam_51_accepted_9_residual_manual_rework", review: { reviewedNails: 60, accepted: 51, rework: 9 } });
  const failedRepair = write("failed-repair.json", { summary: { batch: { pass: 0, suspect: 5, missing: 0 } } });
  const rejection = write("rejection.json", { ok: true, decision: "reject_final_candidate_v1_original_resolution_skin_contamination" });
  const candidate = write("candidate.json", { ok: true, imageCount: 10, polygonCount: 60, retainedPolygonCount: 51, manualPolygonCount: 9, pairwiseOverlapCount: 0 });
  const geometry = write("geometry.json", { summary: { batch: { pass: 60, suspect: 0, missing: 0 } } });
  const review = write("review.json", { ok: true, decision: "mask_review_shard_complete_final_truth_audit_still_required", counts: { images: 10, exclude: 0, pass: 10, rework: 0 } });
  const truth = write("truth.json", { ok: true, decision: "approved_unique_development_evaluation_truth_index", policy: { trainingUse: "prohibited" }, summary: { uniqueImageCount: 33, completeMaskCount: 205, conflictingImageCount: 0 } });
  const prior = write("prior.json", { ok: true, metrics: { incrementalNails: 60, samAccepted: 60, residualManualBoundaryInterventions: 0 } });
  const stage = (durationSeconds: number) => ({ start: "2026-09-15T00:00:00+08:00", end: new Date(Date.parse("2026-09-14T16:00:00Z") + durationSeconds * 1000).toISOString(), durationSeconds });
  const timing = write("timing.json", { stages: { guardedPrelabel: stage(4.9215545), samPcaMultipoint: stage(34.3688273), failedTightRepair: stage(7.3470087), finalCandidateV1Materialization: stage(5.292), finalCandidateV2CorrectionMaterialization: stage(5.1776776), finalOriginalResolutionReview: stage(99.8829805) }, limitations: { manualPolygonAuthoringActiveSeconds: null, suspendedWallTimeExcluded: true } });
  const prelabelScript = write("prelabel.py", "def main():\n    install_read_only_ultralytics_image_check()\n    model = YOLO(str(model_path))\n");
  const output = path.join(root, "output.json");
  const result = spawnSync("python", [script, "--workspace", workspace, "--prelabel-audit", prelabel, "--prompts", prompts, "--sam", sam, "--sam-visual-decision", visual, "--failed-repair-geometry", failedRepair, "--rejected-final-v1", rejection, "--final-candidate", candidate, "--final-geometry", geometry, "--mask-review-final", review, "--truth-index", truth, "--prior-incremental-audit", prior, "--timing", timing, "--prelabel-script", prelabelScript, "--output", output], { encoding: "utf8" });
  assert.equal(result.status, 0, result.stderr);
  return JSON.parse(readFileSync(output, "utf8"));
}

test("第三批标注审计保留一次自动候选后人工止损路线", () => {
  const report = runAudit();
  assert.equal(report.ok, true);
  assert.equal(report.metrics.samAcceptanceRate, 0.85);
  assert.equal(report.metrics.combinedLastTwoBatchSamAcceptanceRate, 0.925);
  assert.equal(report.metrics.cumulativeDevelopmentEvaluationImages, 33);
  assert.equal(report.policy.productState, "hold");
});

test("第三批标注审计拒绝开发评估样本训练授权", () => {
  const report = runAudit("allowed");
  assert.equal(report.ok, false);
  assert.match(report.errors.join("\n"), /role isolation/);
});
