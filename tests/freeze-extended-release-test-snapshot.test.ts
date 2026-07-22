import assert from "node:assert/strict";
import { execFileSync, spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { existsSync, mkdirSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";

const script = path.resolve("model/training/freeze-extended-release-test-snapshot.py");

function hash(value: string | Buffer) {
  return createHash("sha256").update(value).digest("hex");
}

function fileHash(filePath: string) {
  return hash(readFileSync(filePath));
}

function canonicalJson(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(",")}]`;
  if (value && typeof value === "object") {
    return `{${Object.entries(value as Record<string, unknown>)
      .sort(([left], [right]) => left.localeCompare(right))
      .map(([key, item]) => `${JSON.stringify(key)}:${canonicalJson(item)}`)
      .join(",")}}`;
  }
  return JSON.stringify(value);
}

function writeJson(filePath: string, value: unknown) {
  writeFileSync(filePath, JSON.stringify(value));
}

function annotation(fileName: string, sourceGroup: string) {
  return {
    version: "nail-texture-dataset/v1",
    image: { id: path.parse(fileName).name, fileName, width: 100, height: 100, sourceGroup, negative: false },
    annotations: [{
      id: "n1",
      label: "nail_texture",
      polygon: [{ x: 10, y: 10 }, { x: 40, y: 10 }, { x: 40, y: 40 }, { x: 10, y: 40 }],
      attributes: {},
    }],
  };
}

function truthIndex(records: Array<Record<string, unknown>>) {
  return {
    ok: true,
    decision: "approved_truth_index",
    summary: { uniqueImageCount: records.length, conflictingImageCount: 0 },
    canonicalTruths: records,
    conflicts: [],
  };
}

function fixture(overlapTrainSource = false) {
  const root = mkdtempSync(path.join(tmpdir(), "freeze-extended-release-"));
  const baseRoot = path.join(root, "base");
  const baseImages = path.join(baseRoot, "images", "core");
  const baseAnnotations = path.join(baseRoot, "annotations", "core");
  const supplementalRoot = path.join(root, "supplemental");
  mkdirSync(baseImages, { recursive: true });
  mkdirSync(baseAnnotations, { recursive: true });
  mkdirSync(supplementalRoot, { recursive: true });
  const baseFile = "base.jpg";
  const supplementalFile = "supplemental.jpg";
  const baseImage = path.join(baseImages, baseFile);
  const supplementalImage = path.join(supplementalRoot, supplementalFile);
  execFileSync("python", [
    "-c",
    "from PIL import Image; import sys; Image.new('RGB',(100,100),'white').save(sys.argv[1]); Image.new('RGB',(100,100),'black').save(sys.argv[2])",
    baseImage,
    supplementalImage,
  ]);
  const baseAnnotation = path.join(baseAnnotations, "base.json");
  const supplementalAnnotation = path.join(supplementalRoot, "supplemental.json");
  writeJson(baseAnnotation, annotation(baseFile, "base-group"));
  writeJson(supplementalAnnotation, annotation(supplementalFile, "supplemental-group"));
  const baseImageSha = fileHash(baseImage);
  const baseAnnotationSha = fileHash(baseAnnotation);
  const baseRecord = {
    lane: "core",
    fileName: baseFile,
    parentFileName: baseFile,
    sourceGroup: "base-group",
    parentSourceGroup: "base-group",
    imageSha256: baseImageSha,
    annotationSha256: baseAnnotationSha,
    imageAnnotationPairSha256: hash(canonicalJson({ imageSha256: baseImageSha, annotationSha256: baseAnnotationSha })),
    width: 100,
    height: 100,
    maskCount: 1,
    authorizedUses: ["independent-release-test"],
    trainingUse: "prohibited",
  };
  const baseManifest = path.join(baseRoot, "manifest.json");
  writeJson(baseManifest, {
    schemaVersion: 1,
    snapshotId: "base-v1",
    trainingUse: "prohibited",
    counts: { images: 1, masks: 1 },
    itemsSha256: hash(canonicalJson([baseRecord])),
    items: [baseRecord],
  });
  const supplementalImageSha = fileHash(supplementalImage);
  const supplementalAnnotationSha = fileHash(supplementalAnnotation);
  const truthReport = path.join(supplementalRoot, "truth-report.json");
  writeJson(truthReport, {
    ok: true,
    decision: "approved_as_release_test_truth_candidate_pending_snapshot_freeze",
    inputs: {
      truthRole: "release-test",
      image: supplementalImage,
      imageSha256: supplementalImageSha,
      annotation: supplementalAnnotation,
      annotationSha256: supplementalAnnotationSha,
    },
    policy: { targetRole: "release-test", trainingUse: "prohibited" },
    item: {
      fileName: supplementalFile,
      sourceGroup: "supplemental-group",
      completeMaskCount: 1,
      trainingUse: "prohibited",
    },
  });
  const supplementalTruth = {
    reportPath: truthReport,
    reportSha256: fileHash(truthReport),
    fileName: supplementalFile,
    imageSha256: supplementalImageSha,
    sourceGroup: "supplemental-group",
    completeMaskCount: 1,
    annotationPath: supplementalAnnotation,
    annotationSha256: supplementalAnnotationSha,
  };
  const supplementalIndex = path.join(root, "supplemental-index.json");
  const trainIndex = path.join(root, "train-index.json");
  const validationIndex = path.join(root, "validation-index.json");
  writeJson(supplementalIndex, truthIndex([supplementalTruth]));
  writeJson(trainIndex, truthIndex([{
    fileName: "train.jpg",
    imageSha256: "1".repeat(64),
    sourceGroup: overlapTrainSource ? "supplemental-group" : "train-group",
  }]));
  writeJson(validationIndex, truthIndex([{
    fileName: "validation.jpg",
    imageSha256: "2".repeat(64),
    sourceGroup: "validation-group",
  }]));
  return {
    root,
    baseManifest,
    supplementalIndex,
    trainIndex,
    validationIndex,
    outputRoot: path.join(root, "combined"),
    report: path.join(root, "report.json"),
  };
}

function args(item: ReturnType<typeof fixture>) {
  return [
    script,
    "--base-snapshot", item.baseManifest,
    "--supplemental-truth-index", item.supplementalIndex,
    "--train-truth-index", item.trainIndex,
    "--validation-truth-index", item.validationIndex,
    "--output-root", item.outputRoot,
    "--report", item.report,
    "--minimum-representative-images", "2",
  ];
}

test("extended release-test freeze deep-checks and combines isolated truth", () => {
  const item = fixture();
  execFileSync("python", args(item));
  const report = JSON.parse(readFileSync(item.report, "utf8"));
  const manifest = JSON.parse(readFileSync(path.join(item.outputRoot, "manifest.json"), "utf8"));
  assert.equal(report.ok, true);
  assert.equal(manifest.counts.images, 2);
  assert.equal(manifest.counts.masks, 2);
  assert.equal(manifest.representativeReleaseGate.ok, true);
  assert.equal(manifest.sourceIsolation.ok, true);
  assert.equal(manifest.trainingUse, "prohibited");
  assert.equal(existsSync(path.join(item.outputRoot, "images", "core", "supplemental.jpg")), true);
});

test("extended release-test freeze rejects train source-group leakage before output", () => {
  const item = fixture(true);
  const result = spawnSync("python", args(item), { encoding: "utf8" });
  assert.notEqual(result.status, 0);
  const report = JSON.parse(readFileSync(item.report, "utf8"));
  assert.equal(report.ok, false);
  assert.match(report.errors.join("\n"), /train\/release-test sourceGroup overlap/);
  assert.equal(existsSync(item.outputRoot), false);
});
