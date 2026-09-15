import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";

const script = path.resolve("model/training/audit-development-cycle-015-batch4-annotation-acceleration.py");

function runAudit(trainingUse = "prohibited") {
  const root = mkdtempSync(path.join(tmpdir(), "cycle015-batch4-audit-"));
  const write = (name: string, value: unknown) => {
    const target = path.join(root, name);
    writeFileSync(target, typeof value === "string" ? value : JSON.stringify(value));
    return target;
  };
  const stage = (name: string, seconds: number) => ({ stage: name, startedAt: "2026-09-15T00:00:00Z", endedAt: new Date(Date.parse("2026-09-15T00:00:00Z") + seconds * 1000).toISOString(), durationSeconds: seconds });
  const source = write("source.json", { ok: true, decision: "freeze_43_cumulative_source_qualified_candidates_continue_to_133", counts: { generatedImages: 44, sourceQualifiedImages: 43, sourceGroups: 43, fullyVisibleNails: 265, identityOrRoleOverlaps: 0, targetSourceQualifiedImages: 133, remainingSourceQualifiedImages: 90 }, policy: { sourceGateDoesNotPermitTraining: true, protectedOrConsumedDataReused: false } });
  const workspace = write("workspace.json", { ok: true, counts: { images: 10, sourceGroups: 10, shards: 10, expectedFullyVisibleNails: 60, truthFileNameOverlaps: 0, truthImageSha256Overlaps: 0, truthSourceGroupOverlaps: 0, copiedImages: 10, cumulativeSourceQualifiedImages: 43, existingDevelopmentEvaluationTruthImages: 33, pendingIncrementImages: 10 }, policy: { workspaceDoesNotGrantTrainingUse: true, originalResolutionPerNailReviewRequired: true } });
  const prelabel = write("prelabel.json", { ok: true, counts: { images: 10, expectedFullyVisibleNails: 60, candidates: 60, cappedCountCoverage: 0.983333, zeroCandidateImages: 0, underCandidateImages: 1, exactCandidateImages: 8, overCandidateImages: 1, duplicateOverlapPairs: 0, machineErrors: 0 } });
  const prompts = write("prompts.json", { imageCount: 9, promptCount: 55, trimmedOverpredictionCandidateCount: 1, skippedImages: [{ fileName: "0040_masculine_olive_short_natural.png", expected: 5, candidates: 4 }], policy: { trainingUse: "prohibited" } });
  const sam = write("sam.json", { ok: true, imageCount: 9, promptCount: 55, outputs: [{ polygonCount: 55 }], errors: [] });
  const samGeometry = write("sam-geometry.json", { summary: { batch: { pass: 55, suspect: 0, missing: 0 } } });
  const visual = write("visual.json", { ok: true, decision: "sam_55_accepted_zero_residual_rework_for_nine_images", review: { method: "original-resolution full-image overlay and hash-bound 2x per-nail evidence", reviewedImages: 9, reviewedNails: 55, accepted: 55, rework: 0 }, policy: { trimmedOverpredictionCandidateWasConfirmedAtOriginalResolutionAsNonNail: true, modelUndercoverageDidNotChangeTruthDenominator: true } });
  const targeted = write("targeted.json", { ok: true, imageCount: 1, promptCount: 1, outputs: [{ polygonCount: 1 }] });
  const targetedRejection = write("targeted-rejection.json", { ok: true, decision: "reject_0040_missing_thumb_sam_background_segmentation", review: { accepted: 0, rejected: 1 } });
  const detected = write("detected.json", { ok: true, imageCount: 1, promptCount: 4, outputs: [{ polygonCount: 4 }] });
  const detectedRejection = write("detected-rejection.json", { ok: true, decision: "reject_0040_detected_nail_sam_background_contamination", review: { accepted: 1, rejected: 3 } });
  const rejection1 = write("rejection1.json", { ok: true, decision: "reject_batch4_final_candidate_v1_thumb_proximal_undercoverage" });
  const rejection2 = write("rejection2.json", { ok: true, decision: "reject_batch4_final_candidate_v2_correction_target_mismatch" });
  const rejection3 = write("rejection3.json", { ok: true, decision: "reject_batch4_final_candidate_v3_inherited_0044_dual_definition" });
  const final = write("final.json", { ok: true, decision: "candidate_only_not_training_or_test_truth", imageCount: 10, polygonCount: 60, retainedPolygonCount: 55, manualPolygonCount: 5, pairwiseOverlapCount: 0, errors: [] });
  const finalGeometry = write("final-geometry.json", { summary: { batch: { pass: 60, suspect: 0, missing: 0 } } });
  const review = write("review.json", { ok: true, decision: "mask_review_shard_complete_final_truth_audit_still_required", counts: { images: 10, exclude: 0, pass: 10, rework: 0 }, policy: { trainingUse } });
  const truth = write("truth.json", { ok: true, decision: "approved_unique_development_evaluation_truth_index", summary: { approvedReportCount: 43, rejectedReportCount: 0, uniqueImageCount: 43, completeMaskCount: 265, redundantReportCount: 0, redundantImageCount: 0, conflictingImageCount: 0 }, policy: { trainingUse, evaluationUse: "prohibited-until-clean-development-materialization-audit" } });
  const prior = write("prior.json", { ok: true, metrics: { combinedLastTwoBatchNails: 120, combinedLastTwoBatchSamAccepted: 111 } });
  const timingPrelabel = write("timing-prelabel.json", stage("guardedPrelabel", 5.3227996));
  const timingSam = write("timing-sam.json", stage("samPcaMultipoint", 33.7137651));
  const timingTargeted = write("timing-targeted.json", stage("targetedSamMissingThumb", 5.859423));
  const timingReview = write("timing-review.json", stage("finalOriginalResolutionReview", 248.534482));
  const prelabelScript = write("prelabel.py", "def main():\n    install_read_only_ultralytics_image_check()\n    model = YOLO(str(model_path))\n");
  const output = path.join(root, "output.json");
  const args = [script, "--source-audit", source, "--workspace", workspace, "--prelabel-audit", prelabel, "--prompts", prompts, "--sam", sam, "--sam-geometry", samGeometry, "--sam-visual-decision", visual, "--targeted-sam", targeted, "--targeted-sam-rejection", targetedRejection, "--detected-sam", detected, "--detected-sam-rejection", detectedRejection, "--rejected-final-v1", rejection1, "--rejected-final-v2", rejection2, "--rejected-final-v3", rejection3, "--final-candidate", final, "--final-geometry", finalGeometry, "--mask-review-final", review, "--truth-index", truth, "--prior-batch3-audit", prior, "--timing-prelabel", timingPrelabel, "--timing-sam", timingSam, "--timing-targeted", timingTargeted, "--timing-final-review", timingReview, "--prelabel-script", prelabelScript, "--output", output];
  const result = spawnSync("python", args, { encoding: "utf8" });
  assert.equal(result.status, 0, result.stderr);
  return JSON.parse(readFileSync(output, "utf8"));
}

test("第四批标注审计确认计数分流路线并保留全部失败证据", () => {
  const report = runAudit();
  assert.equal(report.ok, true);
  assert.equal(report.metrics.samAcceptanceRate, 55 / 60);
  assert.equal(report.metrics.combinedLastThreeBatchSamAcceptanceRate, 166 / 180);
  assert.equal(report.metrics.cumulativeDevelopmentEvaluationImages, 43);
  assert.equal(report.routeValidation.valid, true);
  assert.equal(report.routeValidation.failedAttemptsPreserved.length, 5);
  assert.equal(report.policy.productState, "hold");
});

test("第四批标注审计拒绝开发评估真值获得训练授权", () => {
  const report = runAudit("allowed");
  assert.equal(report.ok, false);
  assert.match(report.errors.join("\n"), /development truth role|final original-resolution review/);
});
