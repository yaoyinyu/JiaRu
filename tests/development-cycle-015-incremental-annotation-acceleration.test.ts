import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";

const script = path.resolve("model/training/audit-development-cycle-015-incremental-annotation-acceleration.py");

function runAudit(trainingUse = "prohibited") {
  const root = mkdtempSync(path.join(tmpdir(), "cycle015-incremental-audit-"));
  const write = (name: string, value: unknown) => {
    const target = path.join(root, name);
    writeFileSync(target, typeof value === "string" ? value : JSON.stringify(value));
    return target;
  };
  const workspace = write("workspace.json", {
    ok: true,
    counts: { images: 10, expectedFullyVisibleNails: 60 },
    items: Array.from({ length: 10 }, () => ({ assignedRole: "development-evaluation-extension", trainingUse })),
  });
  const prelabel = write("prelabel.json", { ok: true, imageCount: 10, totalCandidates: 63 });
  const comparison = write("comparison.json", { ok: true, decision: "guarded_rerun_is_canonical_prior_run_excluded", differingAnnotationCount: 0 });
  const prompts = write("prompts.json", { imageCount: 10, promptCount: 60, trimmedOverpredictionCandidateCount: 3 });
  const sam = write("sam.json", { ok: true, promptCount: 60, boxOnlyFallbackPromptCount: 0, errors: [], outputs: [{ polygonCount: 60 }] });
  const visual = write("visual.json", { ok: true, review: { reviewedNails: 60, accepted: 60, rework: 0 } });
  const candidate = write("candidate.json", { ok: true, imageCount: 10, polygonCount: 60, manualPolygonCount: 0, pairwiseOverlapCount: 0 });
  const geometry = write("geometry.json", { summary: { batch: { pass: 60, suspect: 0, missing: 0 } } });
  const review = write("review.json", { ok: true, counts: { images: 10, exclude: 0, pass: 10, rework: 0 } });
  const truth = write("truth.json", { ok: true, decision: "approved_unique_development_evaluation_truth_index", policy: { trainingUse: "prohibited" }, summary: { uniqueImageCount: 23, completeMaskCount: 145, conflictingImageCount: 0 } });
  const baseline = write("baseline.json", { ok: true, metrics: { pcaMultipointSamAccepted: 44, nails: 45 } });
  const prelabelScript = write("prelabel.py", "def main():\n    install_read_only_ultralytics_image_check()\n    model = YOLO(str(model_path))\n");
  const output = path.join(root, "output.json");
  const result = spawnSync("python", [script,
    "--workspace", workspace, "--prelabel", prelabel, "--canonical-comparison", comparison,
    "--prompts", prompts, "--sam", sam, "--sam-visual-decision", visual,
    "--final-candidate", candidate, "--final-geometry", geometry, "--mask-review", review,
    "--truth-index", truth, "--baseline-audit", baseline, "--prelabel-script", prelabelScript,
    "--output", output,
  ], { encoding: "utf8" });
  assert.equal(result.status, 0, result.stderr);
  return JSON.parse(readFileSync(output, "utf8"));
}

test("增量标注加速审计接受60/60且保持开发评估隔离", () => {
  const report = runAudit();
  assert.equal(report.ok, true);
  assert.equal(report.metrics.samAcceptanceRate, 1);
  assert.equal(report.metrics.residualManualBoundaryInterventions, 0);
  assert.equal(report.policy.productState, "hold");
});

test("增量标注加速审计拒绝开发评估样本训练授权", () => {
  const report = runAudit("allowed");
  assert.equal(report.ok, false);
  assert.match(report.errors.join("\n"), /role isolation/);
});
