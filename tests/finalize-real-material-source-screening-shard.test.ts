import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";

const script = path.resolve("model/training/finalize-real-material-source-screening-shard.py");
const hash = (file: string) => createHash("sha256").update(readFileSync(file)).digest("hex");

test("screening finalizer requires full coverage and preserves training prohibition", () => {
  const root = mkdtempSync(path.join(tmpdir(), "source-screen-"));
  const shard = path.join(root, "shard.csv");
  writeFileSync(shard, "fileName,sha256,sourceGroup,width,height,reviewStatus,fullyVisibleNails,completeMasks,issueCodes,assignedRole,note\na.jpg,a,g1,10,10,,,,,,\nb.jpg,b,g1,10,10,,,,,,\n");
  const page = path.join(root, "page.jpg"); writeFileSync(page, "page");
  const sheets = path.join(root, "sheets.json");
  writeFileSync(sheets, JSON.stringify({ ok: true, decision: "screening_sheets_ready_original_resolution_review_still_required", inputs: { shard, shardSha256: hash(shard) }, pages: [{ path: page, sha256: hash(page) }] }));
  const decisions = path.join(root, "decisions.json");
  writeFileSync(decisions, JSON.stringify({ sheetsReportSha256: hash(sheets), reviewedPageHashes: { "page.jpg": hash(page) }, items: [{ fileName: "a.jpg", decision: "keep-for-annotation", fullyVisibleNails: 5 }, { fileName: "b.jpg", decision: "exclude-collage" }] }));
  const output = path.join(root, "output");
  const result = spawnSync("python", [script, "--sheets-report", sheets, "--decisions", decisions, "--output-dir", output], { encoding: "utf8" });
  assert.equal(result.status, 0, result.stderr);
  const report = JSON.parse(readFileSync(path.join(output, "source-screening-final.json"), "utf8"));
  assert.equal(report.counts.keptForAnnotation, 1);
  assert.ok(report.items.every((item: { trainingUse: string }) => item.trainingUse === "prohibited"));
  assert.equal(report.policy.sourceScreeningDoesNotApproveMasks, true);
});
