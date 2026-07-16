import assert from "node:assert/strict";
import { execFileSync, spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdirSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";

const script = path.resolve("model/training/build-first-annotation-mask-review-workspace.py");
const hash = (file: string) => createHash("sha256").update(readFileSync(file)).digest("hex");

test("first annotation mask review workspace binds candidates without approving truth", () => {
  const root = mkdtempSync(path.join(tmpdir(), "first-mask-review-"));
  const images = path.join(root, "images");
  const annotations = path.join(root, "annotations");
  const overlays = path.join(root, "overlays");
  mkdirSync(images); mkdirSync(annotations); mkdirSync(overlays);
  for (const name of ["a.jpg", "b.jpg"]) {
    execFileSync("python", ["-c", `from PIL import Image; Image.new('RGB',(160,120),(210,170,150)).save(r'${path.join(images, name)}')`]);
    execFileSync("python", ["-c", `from PIL import Image; Image.new('RGB',(160,120),(180,220,180)).save(r'${path.join(overlays, `${path.parse(name).name}-sam-reviewed-overlay.png`)}')`]);
  }
  const polygon = [{ x: 20, y: 20 }, { x: 50, y: 20 }, { x: 50, y: 60 }, { x: 20, y: 60 }];
  const annotation = (name: string, group: string, annotationsValue: unknown[]) => ({
    version: "nail-texture-dataset/v1", decision: "candidate_only_not_training_truth",
    trainingUse: "prohibited", originalResolutionReviewRequired: true,
    image: { fileName: name, width: 160, height: 120, sourceGroup: group, negative: false },
    annotations: annotationsValue,
  });
  writeFileSync(path.join(annotations, "a.json"), JSON.stringify(annotation("a.jpg", "g1", [])));
  writeFileSync(path.join(annotations, "b.json"), JSON.stringify(annotation("b.jpg", "g1", [{ id: "n1", polygon }])));
  const items = ["a.jpg", "b.jpg"].map((fileName) => ({
    fileName, workspacePath: path.join(images, fileName), sha256: hash(path.join(images, fileName)),
    sourceGroup: "g1", expectedFullyVisibleNails: 1, trainingUse: "prohibited", annotationTruthStatus: "not-started",
  }));
  const workspace = path.join(root, "workspace.json");
  writeFileSync(workspace, JSON.stringify({ ok: true, decision: "annotation_workspace_ready_candidate_only", counts: { images: 2 }, items }));
  const reviewCsv = path.join(root, "prelabel-review.csv");
  writeFileSync(reviewCsv, `fileName,sha256,sourceGroup,expectedFullyVisibleNails,candidateCount,countDelta,reviewPriority,machineGeometryStatus,machineIssueCodes,reviewStatus,note\na.jpg,${items[0].sha256},g1,1,0,-1,critical-zero,pass,,,\nb.jpg,${items[1].sha256},g1,1,1,0,low-exact,pass,,,\n`);
  const prelabel = path.join(root, "prelabel.json");
  writeFileSync(prelabel, JSON.stringify({ ok: true, decision: "prelabel_candidate_audit_pass_original_resolution_review_required", inputs: { workspaceManifestSha256: hash(workspace), reviewCsv, reviewCsvSha256: hash(reviewCsv) } }));
  const sam = path.join(root, "sam.json");
  writeFileSync(sam, JSON.stringify({ ok: true, decision: "sam_candidate_only_not_training_truth", trainingUse: "prohibited", originalResolutionReviewRequired: true, outputs: [
    { fileName: "a.jpg", annotationPath: path.join(annotations, "a.json"), overlayPath: path.join(overlays, "a-sam-reviewed-overlay.png"), polygonCount: 0, sourceGroup: "g1" },
    { fileName: "b.jpg", annotationPath: path.join(annotations, "b.json"), overlayPath: path.join(overlays, "b-sam-reviewed-overlay.png"), polygonCount: 1, sourceGroup: "g1" },
  ] }));
  const geometry = path.join(root, "geometry.json");
  writeFileSync(geometry, JSON.stringify({ decision: "candidate_only_not_training_truth", rows: [{ fileName: "b.jpg", nailIndex: 1, status: "pass", reasons: [] }] }));
  const output = path.join(root, "output");
  const result = spawnSync("python", [script, "--workspace-manifest", workspace, "--prelabel-audit", prelabel, "--sam-report", sam, "--geometry-audit", geometry, "--output-dir", output], { encoding: "utf8" });
  assert.equal(result.status, 0, result.stderr || result.stdout);
  const report = JSON.parse(readFileSync(path.join(output, "mask-review-workspace-report.json"), "utf8"));
  assert.equal(report.ok, true);
  assert.equal(report.counts.images, 2);
  assert.equal(report.counts.zeroCandidateImages, 1);
  assert.equal(report.policy.originalResolutionReviewRequired, true);
  assert.equal(report.policy.trainingUse, "prohibited");
  assert.equal(report.shards.length, 1);
  const csv = readFileSync(report.shards[0].path, "utf8");
  assert.match(csv, /reviewStatus,finalCompleteMaskCount/);
  assert.match(csv, /a\.jpg/);
});
