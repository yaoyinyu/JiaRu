import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";

const script = path.resolve("model/training/finalize-first-annotation-mask-review-shard.py");
const hash = (file: string) => createHash("sha256").update(readFileSync(file)).digest("hex");

test("mask review shard finalizer requires full hash-bound review and keeps training prohibited", () => {
  const root = mkdtempSync(path.join(tmpdir(), "final-mask-review-"));
  const shard = path.join(root, "shard.csv");
  writeFileSync(shard, "fileName,sha256,sourceGroup,expectedFullyVisibleNails,candidateCount\na.jpg,abc,g1,1,1\nb.jpg,def,g2,1,0\n");
  const page = path.join(root, "page.jpg"); writeFileSync(page, "page");
  const workspace = path.join(root, "workspace.json");
  writeFileSync(workspace, JSON.stringify({ ok: true, decision: "first_annotation_mask_review_workspace_ready_original_resolution_review_required", shards: [{ index: 1, path: shard, sha256: hash(shard) }], pages: [{ shardIndex: 1, path: page, sha256: hash(page) }] }));
  const decisions = path.join(root, "decisions.json");
  writeFileSync(decisions, JSON.stringify({ schemaVersion: 1, reviewWorkspaceSha256: hash(workspace), shardIndex: 1, shardSha256: hash(shard), reviewedPageSha256s: [hash(page)], items: [
    { fileName: "a.jpg", sha256: "abc", sourceGroup: "g1", reviewStatus: "pass", finalCompleteMaskCount: 1, issueCodes: [] },
    { fileName: "b.jpg", sha256: "def", sourceGroup: "g2", reviewStatus: "rework", finalCompleteMaskCount: 0, issueCodes: ["missing_all_masks"] },
  ] }));
  const output = path.join(root, "result.json");
  const result = spawnSync("python", [script, "--review-workspace", workspace, "--shard-index", "1", "--decisions", decisions, "--output", output], { encoding: "utf8" });
  assert.equal(result.status, 0, result.stderr || result.stdout);
  const report = JSON.parse(readFileSync(output, "utf8"));
  assert.equal(report.ok, true);
  assert.equal(report.counts.pass, 1);
  assert.equal(report.counts.rework, 1);
  assert.equal(report.policy.trainingUse, "prohibited");
  assert.equal(report.items[0].annotationTruthStatus, "reviewed-candidate-not-final-truth");
});
