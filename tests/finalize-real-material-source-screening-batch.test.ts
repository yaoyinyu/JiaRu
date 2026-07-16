import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdirSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";

const script = path.resolve("model/training/finalize-real-material-source-screening-batch.py");
const hash = (file: string) => createHash("sha256").update(readFileSync(file)).digest("hex");

function fixture() {
  const root = mkdtempSync(path.join(tmpdir(), "source-screen-batch-"));
  const queueDir = path.join(root, "queue");
  const reportsRoot = path.join(root, "reports");
  mkdirSync(queueDir);
  mkdirSync(reportsRoot);
  const queueReport = path.join(queueDir, "queue.json");
  const combined = path.join(queueDir, "all.csv");
  const header = "fileName,sha256,sourceGroup,width,height,reviewStatus,fullyVisibleNails,completeMasks,issueCodes,assignedRole,note\n";
  writeFileSync(combined, `${header}a.jpg,a,g1,10,10,,,,,,\nb.jpg,b,g2,10,10,,,,,,\n`);
  const shards = [
    { index: 1, fileName: "a.jpg", sha256: "a", sourceGroup: "g1", decision: "keep-for-annotation" },
    { index: 2, fileName: "b.jpg", sha256: "b", sourceGroup: "g2", decision: "exclude-collage" },
  ];
  const shardMetadata = shards.map((entry) => {
    const id = String(entry.index).padStart(3, "0");
    const shard = path.join(queueDir, `quality-review-${id}.csv`);
    writeFileSync(shard, `${header}${entry.fileName},${entry.sha256},${entry.sourceGroup},10,10,,,,,,\n`);
    return { index: entry.index, path: shard, sha256: hash(shard), images: 1, sourceGroups: [entry.sourceGroup] };
  });
  writeFileSync(queueReport, JSON.stringify({
    schemaVersion: 1,
    ok: true,
    decision: "quality_review_queue_ready",
    counts: { queuedImages: 2, sourceGroups: 2, shards: 2 },
    combinedReviewCsv: combined,
    combinedReviewCsvSha256: hash(combined),
    shards: shardMetadata,
  }));
  shards.forEach((entry) => {
    const id = String(entry.index).padStart(3, "0");
    const reportDir = path.join(reportsRoot, `source-screening-${id}`);
    mkdirSync(reportDir);
    const sheets = path.join(root, `sheets-${id}.json`);
    writeFileSync(sheets, JSON.stringify({ inputs: {
      queueReportSha256: hash(queueReport),
      shard: shardMetadata[entry.index - 1].path,
      shardSha256: shardMetadata[entry.index - 1].sha256,
    } }));
    writeFileSync(path.join(reportDir, "source-screening-final.json"), JSON.stringify({
      ok: true,
      decision: "source_screening_shard_pass",
      inputs: { sheetsReport: sheets, sheetsReportSha256: hash(sheets) },
      items: [{
        fileName: entry.fileName,
        sha256: entry.sha256,
        sourceGroup: entry.sourceGroup,
        decision: entry.decision,
        trainingUse: "prohibited",
        annotationTruthStatus: "not-started",
      }],
    }));
  });
  return { root, queueReport, reportsRoot };
}

test("batch finalizer proves exact queue coverage and keeps every item prohibited", () => {
  const { root, queueReport, reportsRoot } = fixture();
  const output = path.join(root, "output");
  const result = spawnSync("python", [script, "--queue-report", queueReport, "--reports-root", reportsRoot, "--output-dir", output], { encoding: "utf8" });
  assert.equal(result.status, 0, result.stderr);
  const report = JSON.parse(readFileSync(path.join(output, "source-screening-batch-final.json"), "utf8"));
  assert.equal(report.decision, "source_screening_batch_pass");
  assert.deepEqual(report.counts, {
    images: 2,
    shards: 2,
    sourceGroups: 2,
    keptForAnnotation: 1,
    excluded: 1,
    byDecision: { "keep-for-annotation": 1, "exclude-collage": 1 },
  });
  assert.ok(report.items.every((item: { trainingUse: string }) => item.trainingUse === "prohibited"));
});

test("batch finalizer rejects a missing shard report", () => {
  const { root, queueReport, reportsRoot } = fixture();
  const output = path.join(root, "output");
  const missing = path.join(reportsRoot, "source-screening-002", "source-screening-final.json");
  writeFileSync(missing, JSON.stringify({ ok: false, decision: "rejected_source_screening_shard", items: [] }));
  const result = spawnSync("python", [script, "--queue-report", queueReport, "--reports-root", reportsRoot, "--output-dir", output], { encoding: "utf8" });
  assert.equal(result.status, 1);
  const report = JSON.parse(readFileSync(path.join(output, "source-screening-batch-final.json"), "utf8"));
  assert.equal(report.ok, false);
  assert.ok(report.errors.some((error: string) => error.includes("did not pass")));
});
