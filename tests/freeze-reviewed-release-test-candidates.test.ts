import assert from "node:assert/strict";
import { execFileSync, spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdirSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";

const script = path.resolve("model/training/freeze-reviewed-release-test-candidates.py");

function sha256(filePath: string) {
  return createHash("sha256").update(readFileSync(filePath)).digest("hex");
}

function writeJson(filePath: string, value: unknown) {
  writeFileSync(filePath, JSON.stringify(value));
}

function annotation(fileName: string, sourceGroup: string, overlap = false) {
  return {
    version: "nail-texture-dataset/v1",
    image: { id: path.parse(fileName).name, fileName, width: 100, height: 100, sourceGroup, negative: false },
    annotations: [
      { id: "n1", label: "nail_texture", polygon: [{ x: 10, y: 10 }, { x: 35, y: 10 }, { x: 35, y: 35 }, { x: 10, y: 35 }], attributes: {} },
      { id: "n2", label: "nail_texture", polygon: overlap
        ? [{ x: 25, y: 25 }, { x: 50, y: 25 }, { x: 50, y: 50 }, { x: 25, y: 50 }]
        : [{ x: 60, y: 60 }, { x: 90, y: 60 }, { x: 90, y: 90 }, { x: 60, y: 90 }], attributes: {} },
    ],
  };
}

function fixture(overlap = false, stressOverlap = false) {
  const root = mkdtempSync(path.join(tmpdir(), "freeze-release-test-"));
  const coreImages = path.join(root, "core-images");
  const coreAnnotations = path.join(root, "core-annotations");
  const stressImages = path.join(root, "stress-images");
  const stressAnnotations = path.join(root, "stress-annotations");
  for (const dir of [coreImages, coreAnnotations, stressImages, stressAnnotations]) mkdirSync(dir);
  const coreFile = "core.jpg";
  const stressFile = "stress.png";
  execFileSync("python", ["-c", "from PIL import Image; import sys; Image.new('RGB',(100,100),'white').save(sys.argv[1]); Image.new('RGB',(100,100),'black').save(sys.argv[2])", path.join(coreImages, coreFile), path.join(stressImages, stressFile)]);
  writeJson(path.join(coreAnnotations, "core.json"), annotation(coreFile, "parent-group-core", overlap));
  writeJson(path.join(stressAnnotations, "stress.json"), annotation(stressFile, "derived-group", stressOverlap));
  const authorized = { authorizedUses: ["independent-release-test", "long-term-regression"], trainingUse: "prohibited" };
  const parentIntake = path.join(root, "parent-intake.json");
  writeJson(parentIntake, { ok: true, authorization: authorized, entries: [
    { fileName: coreFile, sha256: sha256(path.join(coreImages, coreFile)), sourceGroup: "parent-group-core", decision: "core", ...authorized },
    { fileName: "parent-stress.jpg", sha256: "a".repeat(64), sourceGroup: "parent-group-stress", decision: "stress", ...authorized },
  ] });
  const stressIntake = path.join(root, "stress-intake.json");
  writeJson(stressIntake, { ok: true, entries: [{ fileName: stressFile, sha256: sha256(path.join(stressImages, stressFile)), sourceGroup: "derived-group", parentFileName: "parent-stress.jpg", parentSha256: "a".repeat(64), parentSourceGroup: "parent-group-stress", regionId: "primary", normalizedBox: [0, 0, 1, 1], decision: "core", ...authorized }] });
  const coreReview = path.join(root, "core-review.json");
  const stressReview = path.join(root, "stress-review.json");
  writeJson(coreReview, { ok: true, counts: { pass: 1, rework: 0 }, passFiles: [coreFile] });
  writeJson(stressReview, { ok: true, counts: { pass: 1, rework: 0 }, passFiles: [stressFile] });
  const summary = path.join(root, "summary.json");
  writeJson(summary, { ok: true, counts: { pass: 2, acceptedMasks: 4, acceptedSourceGroups: 2 }, passParentFiles: [coreFile, "parent-stress.jpg"] });
  return { root, parentIntake, stressIntake, coreReview, stressReview, summary, coreImages, coreAnnotations, stressImages, stressAnnotations, outputRoot: path.join(root, "snapshot"), report: path.join(root, "report.json") };
}

function args(item: ReturnType<typeof fixture>) {
  return [script, "--parent-intake", item.parentIntake, "--review-summary", item.summary, "--core-review", item.coreReview, "--core-image-dir", item.coreImages, "--core-annotations", item.coreAnnotations, "--stress-intake", item.stressIntake, "--stress-review", item.stressReview, "--stress-image-dir", item.stressImages, "--stress-annotations", item.stressAnnotations, "--output-root", item.outputRoot, "--report", item.report, "--minimum-representative-images", "100"];
}

test("reviewed release-test freeze preserves hashes and keeps the representative gate separate", () => {
  const item = fixture();
  execFileSync("python", args(item));
  const report = JSON.parse(readFileSync(item.report, "utf8"));
  const manifest = JSON.parse(readFileSync(path.join(item.outputRoot, "manifest.json"), "utf8"));
  assert.equal(report.ok, true);
  assert.deepEqual(manifest.counts, { images: 2, masks: 4, coreImages: 1, stressImages: 1, parentSourceGroups: 2 });
  assert.deepEqual(manifest.representativeReleaseGate, { ok: false, actual: 2, required: 100, shortfall: 98 });
  assert.equal(manifest.trainingUse, "prohibited");
  assert.match(manifest.itemsSha256, /^[a-f0-9]{64}$/);
});

test("reviewed release-test freeze rejects overlapping accepted polygons", () => {
  const item = fixture(true, true);
  const result = spawnSync("python", args(item), { encoding: "utf8" });
  assert.notEqual(result.status, 0);
  const report = JSON.parse(readFileSync(item.report, "utf8"));
  assert.equal(report.ok, false);
  assert.equal(report.errors.length, 2);
  assert.match(report.errors.join("\n"), /core\.jpg: nails 1 and 2 overlap/);
  assert.match(report.errors.join("\n"), /stress\.png: nails 1 and 2 overlap/);
});
