import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { execFileSync, spawnSync } from "node:child_process";
import { mkdirSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";

const script = path.resolve("model/training/audit-validation-truth-review.py");
const hash = (file: string) => createHash("sha256").update(readFileSync(file)).digest("hex");

function fixture() {
  const root = mkdtempSync(path.join(tmpdir(), "validation-truth-review-"));
  const image = path.join(root, "sample.jpg");
  const overlay = path.join(root, "sample-overlay.png");
  mkdirSync(root, { recursive: true });
  writeFileSync(image, "image");
  writeFileSync(overlay, "overlay");
  const candidate = path.join(root, "candidate.json");
  writeFileSync(candidate, JSON.stringify({ ok: false, decision: "blocked_undeclared_validation_truth_overlaps", inputs: { split: "val" }, overlapBlockers: [{ fileName: "sample.txt" }], outputs: [{ fileName: "sample.txt", imagePath: image, overlayPath: overlay, zoomPaths: [] }] }));
  const review = path.join(root, "review.json");
  writeFileSync(review, JSON.stringify({ candidateReportSha256: hash(candidate), reviewer: "reviewer", reviewMode: "original-resolution-full-image-and-repaired-crops", items: [{ fileName: "sample.txt", decision: "rework", defects: ["overlap"], notes: "needs repair" }] }));
  return { root, candidate, review, output: path.join(root, "audit.json") };
}

test("rejects reviewed validation truth when any image still needs rework", () => {
  const item = fixture();
  execFileSync("python", [script, "--candidate-report", item.candidate, "--review", item.review, "--output", item.output]);
  const report = JSON.parse(readFileSync(item.output, "utf8"));
  assert.equal(report.ok, true);
  assert.equal(report.decision, "rejected_as_calibration_truth");
  assert.equal(report.calibrationTruthEligible, false);
  assert.equal(report.counts.reviewedImages, 1);
});

test("rejects incomplete review coverage", () => {
  const item = fixture();
  const review = JSON.parse(readFileSync(item.review, "utf8"));
  review.items = [];
  writeFileSync(item.review, JSON.stringify(review));
  const result = spawnSync("python", [script, "--candidate-report", item.candidate, "--review", item.review, "--output", item.output], { encoding: "utf8" });
  assert.notEqual(result.status, 0);
  const report = JSON.parse(readFileSync(item.output, "utf8"));
  assert.match(report.errors.join("\n"), /missing review items/);
});
