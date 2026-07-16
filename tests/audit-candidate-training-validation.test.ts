import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { execFileSync, spawnSync } from "node:child_process";
import { mkdirSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";

const auditScript = path.resolve("model/training/audit-candidate-training-validation.py");
const trainScript = path.resolve("model/training/train-yolo-seg.py");
const hash = (file: string) => createHash("sha256").update(readFileSync(file)).digest("hex");

function fixture() {
  const root = mkdtempSync(path.join(tmpdir(), "candidate-training-validation-"));
  const images = path.join(root, "images", "val");
  const labels = path.join(root, "labels", "val");
  mkdirSync(images, { recursive: true });
  mkdirSync(labels, { recursive: true });
  for (const name of ["a", "b"]) {
    writeFileSync(path.join(images, `${name}.jpg`), name);
    writeFileSync(path.join(labels, `${name}.txt`), "0 0.1 0.1 0.3 0.1 0.3 0.3 0.1 0.3\n");
  }
  const dataset = path.join(root, "dataset.yaml");
  writeFileSync(dataset, `path: ${root.replaceAll("\\", "/")}\ntrain: images/train\nval: images/val\ntest: images/test\nnames:\n  0: nail_texture\ntask: segment\nclass_count: 1\nimage_size: 512\n`);
  const sourceReport = path.join(root, "source-report.json");
  writeFileSync(sourceReport, JSON.stringify({ decision: "experiment_only_source_isolated_real_dataset", outputDir: root, splitCounts: { train: 0, val: 2, test: 0 }, groupCounts: { validation: { train: 0, val: 2, test: 0 } } }));
  const truthAudit = path.join(root, "truth-audit.json");
  writeFileSync(truthAudit, JSON.stringify({
    ok: true,
    decision: "approved_as_calibration_truth",
    calibrationTruthEligible: true,
    inputs: { split: "val", datasetYaml: dataset, datasetYamlSha256: hash(dataset) },
    counts: { expectedImages: 2, reviewedImages: 2, pass: 2, rework: 0, exclude: 0 },
    labelSha256: { "a.txt": hash(path.join(labels, "a.txt")), "b.txt": hash(path.join(labels, "b.txt")) },
  }));
  return { root, dataset, sourceReport, truthAudit, report: path.join(root, "candidate-validation.json") };
}

function auditArgs(item: ReturnType<typeof fixture>) {
  return [auditScript, "--dataset", item.dataset, "--source-isolation-report", item.sourceReport, "--truth-audit", item.truthAudit, "--min-validation-images", "2", "--output", item.report];
}

test("approves fully bound source-isolated candidate training validation", () => {
  const item = fixture();
  execFileSync("python", auditArgs(item));
  const report = JSON.parse(readFileSync(item.report, "utf8"));
  assert.equal(report.ok, true);
  assert.equal(report.candidateTrainingEligible, true);
  const plan = JSON.parse(execFileSync("python", [trainScript, "--dataset", item.dataset, "--candidate-mode", "--candidate-validation-report", item.report, "--dry-run"], { encoding: "utf8" }));
  assert.equal(plan.training_intent, "candidate");
  assert.equal(plan.candidate_validation_evidence.decision, "approved_candidate_training_validation");
});

test("rejects a validation source group that leaks into training", () => {
  const item = fixture();
  const source = JSON.parse(readFileSync(item.sourceReport, "utf8"));
  source.groupCounts.validation.train = 1;
  writeFileSync(item.sourceReport, JSON.stringify(source));
  const result = spawnSync("python", auditArgs(item), { encoding: "utf8" });
  assert.notEqual(result.status, 0);
  const report = JSON.parse(readFileSync(item.report, "utf8"));
  assert.match(report.errors.join("\n"), /leaks into train or test/);
});

test("candidate training mode refuses missing or rejected evidence", () => {
  const item = fixture();
  const missing = spawnSync("python", [trainScript, "--dataset", item.dataset, "--candidate-mode", "--dry-run"], { encoding: "utf8" });
  assert.notEqual(missing.status, 0);
  writeFileSync(item.report, JSON.stringify({ ok: false, candidateTrainingEligible: false, decision: "rejected_candidate_training_validation" }));
  const rejected = spawnSync("python", [trainScript, "--dataset", item.dataset, "--candidate-mode", "--candidate-validation-report", item.report, "--dry-run"], { encoding: "utf8" });
  assert.notEqual(rejected.status, 0);
  assert.match(rejected.stderr, /not approved/);
});
