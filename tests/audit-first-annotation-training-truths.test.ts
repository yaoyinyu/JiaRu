import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";

const script = path.resolve("model/training/audit-first-annotation-training-truths.py");
const hash = (value: string) => createHash("sha256").update(value).digest("hex");
const hashFile = (file: string) => createHash("sha256").update(readFileSync(file)).digest("hex");

function writeTruth(root: string, name: string, fileName: string, annotationHash: string, masks = 5) {
  const report = {
    ok: true,
    decision: "approved_as_training_truth_candidate_pending_dataset_materialization",
    inputs: { annotation: path.join(root, `${fileName}.json`), annotationSha256: annotationHash },
    item: {
      fileName,
      sha256: hash(fileName),
      sourceGroup: `group-${fileName}`,
      completeMaskCount: masks,
    },
  };
  writeFileSync(path.join(root, name), `${JSON.stringify(report)}\n`);
}

test("training truth index counts identical duplicate reports once", () => {
  const root = mkdtempSync(path.join(tmpdir(), "training-truth-index-"));
  writeTruth(root, "training-truth-003-a-final.json", "a.jpg", "annotation-a", 4);
  writeTruth(root, "training-truth-039-a-final.json", "a.jpg", "annotation-a", 4);
  writeTruth(root, "training-truth-040-b-final.json", "b.jpg", "annotation-b", 5);
  const output = path.join(root, "report.json");
  const run = spawnSync("python", [script, "--truth-dir", root, "--output", output], { encoding: "utf8" });
  assert.equal(run.status, 0, run.stderr || run.stdout);
  const report = JSON.parse(readFileSync(output, "utf8"));
  assert.deepEqual(report.summary, {
    approvedReportCount: 3,
    rejectedReportCount: 0,
    uniqueImageCount: 2,
    completeMaskCount: 9,
    redundantReportCount: 1,
    redundantImageCount: 1,
    conflictingImageCount: 0,
  });
  assert.equal(report.canonicalTruths[0].reportName, "training-truth-039-a-final.json");
});

test("training truth index rejects conflicting reports for the same image", () => {
  const root = mkdtempSync(path.join(tmpdir(), "training-truth-index-conflict-"));
  writeTruth(root, "training-truth-001-a-final.json", "a.jpg", "annotation-old");
  writeTruth(root, "training-truth-002-a-final.json", "a.jpg", "annotation-new");
  const output = path.join(root, "report.json");
  const run = spawnSync("python", [script, "--truth-dir", root, "--output", output], { encoding: "utf8" });
  assert.notEqual(run.status, 0);
  const report = JSON.parse(readFileSync(output, "utf8"));
  assert.equal(report.summary.conflictingImageCount, 1);
  assert.match(report.errors.join("\n"), /conflicting finalized truth reports/);
});

test("validation truth index accepts only validation reports and keeps training prohibited", () => {
  const root = mkdtempSync(path.join(tmpdir(), "validation-truth-index-"));
  const report = {
    ok: true,
    decision: "approved_as_validation_truth_candidate_pending_dataset_materialization",
    inputs: { annotation: path.join(root, "val-a.json"), annotationSha256: "val-annotation-a" },
    item: {
      fileName: "val-a.jpg",
      sha256: hash("val-a.jpg"),
      sourceGroup: "val-group-a",
      completeMaskCount: 2,
    },
  };
  writeFileSync(path.join(root, "validation-truth-001-val-a-final.json"), `${JSON.stringify(report)}\n`);
  const output = path.join(root, "report.json");
  const run = spawnSync("python", [script, "--truth-dir", root, "--truth-role", "val", "--output", output], { encoding: "utf8" });
  assert.equal(run.status, 0, run.stderr || run.stdout);
  const index = JSON.parse(readFileSync(output, "utf8"));
  assert.equal(index.decision, "approved_unique_validation_truth_index");
  assert.equal(index.inputs.reportPattern, "validation-truth-*-final.json");
  assert.equal(index.summary.uniqueImageCount, 1);
  assert.equal(index.summary.completeMaskCount, 2);
  assert.equal(index.policy.trainingUse, "prohibited");
  assert.equal(index.policy.validationUse, "prohibited-until-materialization-audit");
});

test("release-test truth index rejects outer-only forged evidence", () => {
  const root = mkdtempSync(path.join(tmpdir(), "release-test-truth-index-"));
  const image = path.join(root, "release-a.jpg");
  const annotation = path.join(root, "release-a.json");
  const visualReview = path.join(root, "release-a-review.json");
  const roleManifest = path.join(root, "release-role.json");
  writeFileSync(image, "release-image-bytes");
  writeFileSync(annotation, JSON.stringify({ annotations: [{ polygon: [1, 2, 3] }] }));
  writeFileSync(visualReview, JSON.stringify({ ok: true }));
  writeFileSync(roleManifest, JSON.stringify({
    ok: true,
    decision: "annotation_workspace_ready_candidate_only",
    policy: {
      selectionMode: "independent-release-test",
      assignedRole: "independent-release-test",
    },
    items: [{
      fileName: "release-a.jpg",
      sha256: hashFile(image),
      sourceGroup: "release-group-a",
      assignedRole: "independent-release-test",
      expectedFullyVisibleNails: 1,
      trainingUse: "prohibited",
    }],
  }));
  const report = {
    ok: true,
    decision: "approved_as_release_test_truth_candidate_pending_snapshot_freeze",
    inputs: {
      truthRole: "release-test",
      visualReviewFinal: visualReview,
      visualReviewFinalSha256: hashFile(visualReview),
      image,
      imageSha256: hashFile(image),
      annotation,
      annotationSha256: hashFile(annotation),
      roleManifest,
      roleManifestSha256: hashFile(roleManifest),
    },
    policy: {
      snapshotFreezeAndSourceIsolationStillRequired: true,
      trainingUse: "prohibited",
      evaluationUse: "prohibited-until-snapshot-freeze",
    },
    item: {
      fileName: "release-a.jpg",
      sha256: hashFile(image),
      sourceGroup: "release-group-a",
      completeMaskCount: 1,
      annotationTruthStatus: "approved-as-release-test-truth-candidate",
      trainingUse: "prohibited",
      evaluationUse: "prohibited-until-snapshot-freeze",
    },
  };
  writeFileSync(
    path.join(root, "release-test-truth-001-release-a-final.json"),
    `${JSON.stringify(report)}\n`,
  );
  const output = path.join(root, "report.json");
  const run = spawnSync("python", [
    script,
    "--truth-dir", root,
    "--truth-role", "release-test",
    "--output", output,
  ], { encoding: "utf8" });
  assert.notEqual(run.status, 0);
  const index = JSON.parse(readFileSync(output, "utf8"));
  assert.equal(index.decision, "reject_release_test_truth_index");
  assert.match(index.errors.join("\n"), /truth deep replay failed/);
});

test("truth index rejects a directory containing only rejected reports", () => {
  const root = mkdtempSync(path.join(tmpdir(), "release-test-truth-empty-index-"));
  writeFileSync(
    path.join(root, "release-test-truth-001-rejected-final.json"),
    `${JSON.stringify({
      ok: false,
      decision: "reject_release_test_truth_candidate",
      errors: ["not reviewed"],
    })}\n`,
  );
  const output = path.join(root, "index.json");
  const run = spawnSync("python", [
    script,
    "--truth-dir", root,
    "--truth-role", "release-test",
    "--output", output,
  ], { encoding: "utf8" });
  assert.notEqual(run.status, 0);
  const index = JSON.parse(readFileSync(output, "utf8"));
  assert.equal(index.decision, "reject_release_test_truth_index");
  assert.equal(index.summary.approvedReportCount, 0);
  assert.equal(index.summary.rejectedReportCount, 1);
  assert.match(index.errors.join("\n"), /requires at least one approved candidate/);
});

test("truth index output cannot overwrite a finalized report", () => {
  const root = mkdtempSync(path.join(tmpdir(), "training-truth-output-alias-"));
  const reportPath = path.join(root, "training-truth-001-a-final.json");
  writeTruth(root, path.basename(reportPath), "a.jpg", "annotation-a", 4);
  const before = hashFile(reportPath);
  const run = spawnSync("python", [
    script,
    "--truth-dir", root,
    "--output", reportPath,
  ], { encoding: "utf8" });
  assert.notEqual(run.status, 0);
  assert.equal(hashFile(reportPath), before);
  assert.match(run.stderr, /output must not overwrite input evidence/);
});
