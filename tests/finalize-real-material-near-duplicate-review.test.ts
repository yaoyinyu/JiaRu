import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdirSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";

const script = path.resolve("model/training/finalize-real-material-near-duplicate-review.py");
const hash = (file: string) => createHash("sha256").update(readFileSync(file)).digest("hex");

test("finalizer requires full page acknowledgement and pair coverage", () => {
  const root = mkdtempSync(path.join(tmpdir(), "near-final-"));
  const csv = path.join(root, "review.csv");
  const page = path.join(root, "page.jpg");
  writeFileSync(page, "page");
  writeFileSync(csv, "pairId,kind,leftName,rightName,leftSourceGroup,rightSourceGroup,distance,pixelMae,aspectRatioDelta,highSimilarity,recommendedReview,decision,note\nnear-0001,cross-corpus,new.jpg,old.jpg,g1,old,0,0,0,True,review,,\nnear-0002,batch,a.jpg,b.jpg,g2,g2,1,0.1,0,False,review,,\n", "utf8");
  const report = path.join(root, "report.json");
  writeFileSync(report, JSON.stringify({ ok: true, decision: "near_duplicate_visual_review_required", reviewCsv: csv, reviewCsvSha256: hash(csv), pages: [{ path: page, sha256: hash(page) }] }));
  const decisions = path.join(root, "decisions.json");
  writeFileSync(decisions, JSON.stringify({ reviewReportSha256: hash(report), reviewedPageHashes: { "page.jpg": hash(page) }, reviewer: "tester", reviewedAt: "2026-07-16", method: "original-resolution", rules: [{ pairIds: "near-0001", decision: "duplicate-existing-exclude-left" }] }));
  const rejected = spawnSync("python", [script, "--review-report", report, "--decisions", decisions, "--output-dir", path.join(root, "rejected")], { encoding: "utf8" });
  assert.notEqual(rejected.status, 0);
  assert.match(readFileSync(path.join(root, "rejected", "near-duplicate-review-final.json"), "utf8"), /unreviewed pairs/);

  writeFileSync(decisions, JSON.stringify({ reviewReportSha256: hash(report), reviewedPageHashes: { "page.jpg": hash(page) }, reviewer: "tester", reviewedAt: "2026-07-16", method: "original-resolution", rules: [{ pairIds: "near-0001", decision: "duplicate-existing-exclude-left" }, { pairIds: ["near-0002"], decision: "duplicate-batch-keep-left" }] }));
  const passed = spawnSync("python", [script, "--review-report", report, "--decisions", decisions, "--output-dir", path.join(root, "passed")], { encoding: "utf8" });
  assert.equal(passed.status, 0, passed.stderr);
  const result = JSON.parse(readFileSync(path.join(root, "passed", "near-duplicate-review-final.json"), "utf8"));
  assert.equal(result.ok, true);
  assert.equal(result.counts.pairs, 2);
  assert.deepEqual(result.excludedCandidates.map((item: { fileName: string }) => item.fileName), ["b.jpg", "new.jpg"]);
});
