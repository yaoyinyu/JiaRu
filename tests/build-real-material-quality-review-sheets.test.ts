import assert from "node:assert/strict";
import { execFileSync, spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdirSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";

const script = path.resolve("model/training/build-real-material-quality-review-sheets.py");
const hash = (file: string) => createHash("sha256").update(readFileSync(file)).digest("hex");

test("quality review sheets bind shard and images without approving them", () => {
  const root = mkdtempSync(path.join(tmpdir(), "quality-sheets-"));
  const images = path.join(root, "images");
  mkdirSync(images);
  const image = path.join(images, "a.jpg");
  execFileSync("python", ["-c", `from PIL import Image; Image.new('RGB',(120,180),(200,160,140)).save(r'${image}')`]);
  const shard = path.join(root, "shard.csv");
  writeFileSync(shard, `fileName,sha256,sourceGroup,width,height,reviewStatus,fullyVisibleNails,completeMasks,issueCodes,assignedRole,note\na.jpg,${hash(image)},g1,120,180,,,,,,\n`, "utf8");
  const workspace = path.join(root, "workspace.json");
  writeFileSync(workspace, JSON.stringify({ inputs: { root: images } }));
  const queue = path.join(root, "queue.json");
  writeFileSync(queue, JSON.stringify({ ok: true, decision: "quality_review_queue_ready", inputs: { workspaceReport: workspace, workspaceReportSha256: hash(workspace) }, shards: [{ index: 1, path: shard, sha256: hash(shard) }] }));
  const output = path.join(root, "output");
  const result = spawnSync("python", [script, "--queue-report", queue, "--shard-index", "1", "--output-dir", output], { encoding: "utf8" });
  assert.equal(result.status, 0, result.stderr);
  const report = JSON.parse(readFileSync(path.join(output, "quality-review-sheets-report.json"), "utf8"));
  assert.equal(report.ok, true);
  assert.equal(report.counts.images, 1);
  assert.equal(report.policy.contactSheetsCannotApproveImages, true);
  assert.equal(report.pages.length, 1);
});
