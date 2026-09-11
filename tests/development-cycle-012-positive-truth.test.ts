import assert from "node:assert/strict";
import { execFileSync, spawnSync } from "node:child_process";
import { mkdirSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";

const script = path.resolve("model/training/audit-development-cycle-012-positive-truth.py");

test("cycle012 truth audit accepts exactly 13 reviewed five-mask images and rejects overlap", () => {
  const root = mkdtempSync(path.join(tmpdir(), "cycle012-truth-"));
  const images = path.join(root, "images");
  const annotations = path.join(root, "annotations");
  mkdirSync(images); mkdirSync(annotations);
  const items = [];
  const reviewItems = [];
  for (let index = 0; index < 13; index += 1) {
    const fileName = `image-${index}.png`;
    execFileSync("python", ["-c", "from PIL import Image; import sys; Image.new('RGB',(100,100),'white').save(sys.argv[1])", path.join(images, fileName)]);
    const imageSha256 = execFileSync("python", ["-c", "import hashlib,sys; print(hashlib.sha256(open(sys.argv[1],'rb').read()).hexdigest())", path.join(images, fileName)], { encoding: "utf8" }).trim();
    const masks = Array.from({ length: 5 }, (_, nail) => ({ id: `n${nail + 1}`, label: "nail_texture", polygon: [{ x: nail * 18 + 1, y: 10 }, { x: nail * 18 + 15, y: 10 }, { x: nail * 18 + 15, y: 30 }, { x: nail * 18 + 1, y: 30 }], attributes: {} }));
    const annotationPath = path.join(annotations, `image-${index}.json`);
    writeFileSync(annotationPath, JSON.stringify({ version: "nail-texture-dataset/v1", decision: "candidate_only_not_training_truth", trainingUse: "prohibited", originalResolutionReviewRequired: true, image: { fileName, width: 100, height: 100, sourceGroup: `group-${index}` }, annotations: masks }));
    const annotationSha256 = execFileSync("python", ["-c", "import hashlib,sys; print(hashlib.sha256(open(sys.argv[1],'rb').read()).hexdigest())", annotationPath], { encoding: "utf8" }).trim();
    const evidencePath = path.join(root, `evidence-${index}.txt`); writeFileSync(evidencePath, "reviewed");
    const evidenceSha256 = execFileSync("python", ["-c", "import hashlib,sys; print(hashlib.sha256(open(sys.argv[1],'rb').read()).hexdigest())", evidencePath], { encoding: "utf8" }).trim();
    items.push({ fileName, sha256: imageSha256, sourceGroup: `group-${index}`, coverageIntents: ["low-contrast-or-transparent-complete-nails"] });
    reviewItems.push({ fileName, imageSha256, annotationPath, annotationSha256, sourceGroup: `group-${index}`, reviewScale: "original-resolution", reviewDecision: "pass_complete_mask_candidate_only", expectedFullyVisibleNails: 5, completeMaskCount: 5, missingNails: 0, duplicateMasks: 0, contaminatedMasks: 0, evidencePath, evidenceSha256, trainingUse: "prohibited" });
  }
  const plan = path.join(root, "plan.json"); writeFileSync(plan, JSON.stringify({ cycleId: "nail-texture-development-cycle-012", targetedPositiveSelectionContract: { images: 13, masks: 65 } }));
  const source = path.join(root, "source.json"); writeFileSync(source, JSON.stringify({ ok: true, decision: "development_cycle_012_source_selection_pass_candidate_only", trainingUse: "prohibited", counts: { images: 13, sourceGroups: 13, expectedFullyVisibleNails: 65 }, items }));
  const sourceSha256 = execFileSync("python", ["-c", "import hashlib,sys; print(hashlib.sha256(open(sys.argv[1],'rb').read()).hexdigest())", source], { encoding: "utf8" }).trim();
  const review = path.join(root, "review.json"); writeFileSync(review, JSON.stringify({ decision: "development_cycle_012_original_resolution_mask_review_pass_candidate_only", trainingUse: "prohibited", sourceSelectionAudit: { path: source, sha256: sourceSha256 }, items: reviewItems }));
  const output = path.join(root, "report.json");
  const args = [script, "--plan", plan, "--source-selection-audit", source, "--review-manifest", review, "--image-dir", images, "--annotation-dir", annotations, "--output", output];
  execFileSync("python", args);
  const report = JSON.parse(readFileSync(output, "utf8"));
  assert.deepEqual(report.counts, { images: 13, sourceGroups: 13, masks: 65, invalidPolygons: 0, pairwiseOverlaps: 0 });
  execFileSync("python", [script, "--verify-report", output]);
  const broken = JSON.parse(readFileSync(path.join(annotations, "image-0.json"), "utf8"));
  broken.annotations[1].polygon = broken.annotations[0].polygon;
  writeFileSync(path.join(annotations, "image-0.json"), JSON.stringify(broken));
  const failed = spawnSync("python", [script, "--verify-report", output], { encoding: "utf8" });
  assert.notEqual(failed.status, 0);
});
