import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";

const script = path.resolve("model/training/audit-first-annotation-training-truths.py");
const hash = (value: string) => createHash("sha256").update(value).digest("hex");

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
