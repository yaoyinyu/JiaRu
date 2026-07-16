import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";

const script = path.resolve("model/training/build-real-material-quality-review-queue.py");
const hash = (file: string) => createHash("sha256").update(readFileSync(file)).digest("hex");

test("quality queue removes adjudicated exclusions and keeps source groups atomic", () => {
  const root = mkdtempSync(path.join(tmpdir(), "quality-queue-"));
  const reviewCsv = path.join(root, "review.csv");
  writeFileSync(reviewCsv, "fileName,sha256,sourceGroup,width,height,reviewStatus,fullyVisibleNails,completeMasks,issueCodes,assignedRole,note\na.jpg,a,g1,10,10,,,,,,\nb.jpg,b,g1,10,10,,,,,,\nc.jpg,c,g2,10,10,,,,,,\n", "utf8");
  const workspace = path.join(root, "workspace.json");
  writeFileSync(workspace, JSON.stringify({ ok: true, decision: "review_workspace_ready_unreviewed", combinedReviewCsv: reviewCsv, combinedReviewCsvSha256: hash(reviewCsv) }));
  const duplicate = path.join(root, "duplicate.json");
  writeFileSync(duplicate, JSON.stringify({ ok: true, decision: "near_duplicate_visual_review_pass", excludedCandidates: [{ fileName: "c.jpg" }] }));
  const output = path.join(root, "output");
  const result = spawnSync("python", [script, "--workspace-report", workspace, "--near-duplicate-final", duplicate, "--output-dir", output, "--target-shard-size", "1"], { encoding: "utf8" });
  assert.equal(result.status, 0, result.stderr);
  const report = JSON.parse(readFileSync(path.join(output, "quality-review-queue-report.json"), "utf8"));
  assert.equal(report.ok, true);
  assert.equal(report.counts.queuedImages, 2);
  assert.equal(report.counts.shards, 1);
  assert.equal(report.counts.largestShard, 2);
  assert.deepEqual(report.shards[0].sourceGroups, ["g1"]);
  assert.doesNotMatch(readFileSync(report.combinedReviewCsv, "utf8"), /c\.jpg/);
});
