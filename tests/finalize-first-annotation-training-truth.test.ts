import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";
import sharp from "sharp";

const script = path.resolve("model/training/finalize-first-annotation-training-truth.py");
const hash = (file: string) => createHash("sha256").update(readFileSync(file)).digest("hex");

test("training truth finalizer requires visual evidence, valid polygons, and zero overlap", async () => {
  const root = mkdtempSync(path.join(tmpdir(), "final-training-truth-"));
  const image = path.join(root, "a.png");
  await sharp({ create: { width: 20, height: 20, channels: 3, background: "white" } }).png().toFile(image);
  const annotation = path.join(root, "a.json");
  const polygon = [{ x: 2, y: 2 }, { x: 8, y: 2 }, { x: 8, y: 8 }, { x: 2, y: 8 }];
  writeFileSync(annotation, JSON.stringify({ image: { fileName: "a.png", sourceGroup: "g1", width: 20, height: 20 }, annotations: [{ polygon }] }));
  const repair = path.join(root, "repair.json");
  writeFileSync(repair, JSON.stringify({ ok: true, decision: "mask_repair_review_complete_final_truth_audit_still_required", inputs: { annotation, annotationSha256: hash(annotation) }, item: { fileName: "a.png", sha256: hash(image), sourceGroup: "g1", expectedFullyVisibleNails: 1, reviewStatus: "pass", annotationTruthStatus: "reviewed-repair-candidate-not-final-truth" } }));
  const output = path.join(root, "output.json");
  const run = spawnSync("python", [script, "--repair-final", repair, "--image", image, "--output", output], { encoding: "utf8" });
  assert.equal(run.status, 0, run.stderr || run.stdout);
  const report = JSON.parse(readFileSync(output, "utf8"));
  assert.equal(report.item.annotationTruthStatus, "approved-as-training-truth-candidate");
  assert.equal(report.item.trainingUse, "prohibited-until-materialization-audit");

  const overlapping = [{ polygon }, { polygon: [{ x: 5, y: 5 }, { x: 10, y: 5 }, { x: 10, y: 10 }, { x: 5, y: 10 }] }];
  writeFileSync(annotation, JSON.stringify({ image: { fileName: "a.png", sourceGroup: "g1", width: 20, height: 20 }, annotations: overlapping }));
  const changed = JSON.parse(readFileSync(repair, "utf8")); changed.inputs.annotationSha256 = hash(annotation); changed.item.expectedFullyVisibleNails = 2; writeFileSync(repair, JSON.stringify(changed));
  const rejected = spawnSync("python", [script, "--repair-final", repair, "--image", image, "--output", output], { encoding: "utf8" });
  assert.notEqual(rejected.status, 0);
  assert.match(readFileSync(output, "utf8"), /overlap/);
});

test("training truth finalizer accepts a hash-bound direct mask-review pass", async () => {
  const root = mkdtempSync(path.join(tmpdir(), "final-direct-training-truth-"));
  const image = path.join(root, "direct.png");
  await sharp({ create: { width: 24, height: 24, channels: 3, background: "white" } }).png().toFile(image);
  const annotation = path.join(root, "direct.json");
  writeFileSync(annotation, JSON.stringify({
    image: { fileName: "direct.png", sourceGroup: "g-direct", width: 24, height: 24 },
    annotations: [
      { polygon: [{ x: 2, y: 2 }, { x: 8, y: 2 }, { x: 8, y: 8 }, { x: 2, y: 8 }] },
      { polygon: [{ x: 12, y: 12 }, { x: 20, y: 12 }, { x: 20, y: 20 }, { x: 12, y: 20 }] },
    ],
  }));
  const shard = path.join(root, "mask-review-001.csv");
  writeFileSync(
    shard,
    [
      "fileName,sha256,sourceGroup,expectedFullyVisibleNails,candidateCount,annotationSha256",
      `direct.png,${hash(image)},g-direct,2,2,${hash(annotation)}`,
      "",
    ].join("\n"),
  );
  const review = path.join(root, "mask-review-final.json");
  writeFileSync(review, JSON.stringify({
    ok: true,
    decision: "mask_review_shard_complete_final_truth_audit_still_required",
    inputs: { shard, shardSha256: hash(shard) },
    policy: { originalResolutionReviewCompleted: true },
    items: [{
      fileName: "direct.png",
      sha256: hash(image),
      sourceGroup: "g-direct",
      expectedFullyVisibleNails: 2,
      candidateCount: 2,
      reviewStatus: "pass",
      finalCompleteMaskCount: 2,
      annotationTruthStatus: "reviewed-candidate-not-final-truth",
    }],
  }));
  const output = path.join(root, "output.json");
  const run = spawnSync("python", [
    script,
    "--mask-review-final", review,
    "--annotation", annotation,
    "--image", image,
    "--output", output,
  ], { encoding: "utf8" });
  assert.equal(run.status, 0, run.stderr || run.stdout);
  const report = JSON.parse(readFileSync(output, "utf8"));
  assert.equal(report.inputs.visualReviewType, "direct-mask-review");
  assert.equal(report.item.completeMaskCount, 2);
  assert.equal(report.item.annotationTruthStatus, "approved-as-training-truth-candidate");

  const roleManifest = path.join(root, "val-workspace.json");
  writeFileSync(roleManifest, JSON.stringify({
    ok: true,
    decision: "annotation_workspace_ready_candidate_only",
    policy: { selectionMode: "val", assignedRole: "val" },
    items: [{
      fileName: "direct.png",
      sha256: hash(image),
      sourceGroup: "g-direct",
      assignedRole: "val",
      expectedFullyVisibleNails: 2,
      trainingUse: "prohibited",
    }],
  }));
  const valOutput = path.join(root, "val-output.json");
  const valRun = spawnSync("python", [
    script,
    "--mask-review-final", review,
    "--annotation", annotation,
    "--image", image,
    "--truth-role", "val",
    "--role-manifest", roleManifest,
    "--output", valOutput,
  ], { encoding: "utf8" });
  assert.equal(valRun.status, 0, valRun.stderr || valRun.stdout);
  const valReport = JSON.parse(readFileSync(valOutput, "utf8"));
  assert.equal(valReport.decision, "approved_as_validation_truth_candidate_pending_dataset_materialization");
  assert.equal(valReport.inputs.truthRole, "val");
  assert.equal(valReport.item.annotationTruthStatus, "approved-as-validation-truth-candidate");
  assert.equal(valReport.item.trainingUse, "prohibited");
  assert.equal(valReport.item.validationUse, "prohibited-until-materialization-audit");
});
