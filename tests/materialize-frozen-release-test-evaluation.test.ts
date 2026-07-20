import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { execFileSync, spawnSync } from "node:child_process";
import {
  existsSync,
  mkdirSync,
  readFileSync,
  readdirSync,
  writeFileSync,
} from "node:fs";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";

const script = path.resolve("model/training/materialize-frozen-release-test-evaluation.py");
const sha = (value: Buffer | string) => createHash("sha256").update(value).digest("hex");

function canonical(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  if (value && typeof value === "object") {
    return `{${Object.entries(value as Record<string, unknown>)
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([key, item]) => `${JSON.stringify(key)}:${canonical(item)}`)
      .join(",")}}`;
  }
  return JSON.stringify(value);
}

type FrozenItem = {
  lane: "core" | "stress";
  fileName: string;
  parentFileName: string;
  sourceGroup: string;
  parentSourceGroup: string;
  imageSha256: string;
  annotationSha256: string;
  imageAnnotationPairSha256: string;
  width: number;
  height: number;
  maskCount: number;
  authorizedUses: string[];
  trainingUse: "prohibited";
};

function listFiles(root: string, current = root): string[] {
  const files: string[] = [];
  for (const entry of readdirSync(current, { withFileTypes: true })) {
    const target = path.join(current, entry.name);
    if (entry.isDirectory()) files.push(...listFiles(root, target));
    else if (entry.isFile()) files.push(path.relative(root, target).split(path.sep).join("/"));
  }
  return files.sort();
}

function writeManifest(snapshot: string, items: FrozenItem[]) {
  const manifest = {
    snapshotId: "snapshot-v2",
    decision: "frozen_reviewed_candidate_not_release_ready",
    trainingUse: "prohibited",
    counts: {
      images: items.length,
      masks: items.reduce((total, item) => total + item.maskCount, 0),
      coreImages: items.filter((item) => item.lane === "core").length,
      stressImages: items.filter((item) => item.lane === "stress").length,
    },
    itemsSha256: sha(canonical(items)),
    items,
  };
  writeFileSync(path.join(snapshot, "manifest.json"), JSON.stringify(manifest));
  return manifest;
}

function fixture() {
  const root = mkdtempSync(path.join(tmpdir(), "frozen-evaluation-"));
  const snapshot = path.join(root, "snapshot");
  const output = path.join(root, "evaluation");
  const report = `${output}-report.json`;
  const dataset = path.join(root, "training");
  const sources = path.join(dataset, "metadata", "sources.csv");
  for (const lane of ["core", "stress"] as const) {
    mkdirSync(path.join(snapshot, "images", lane), { recursive: true });
    mkdirSync(path.join(snapshot, "annotations", lane), { recursive: true });
  }
  mkdirSync(path.join(dataset, "images", "raw"), { recursive: true });
  mkdirSync(path.dirname(sources), { recursive: true });

  const coreImage = path.join(snapshot, "images", "core", "core.png");
  const stressImage = path.join(snapshot, "images", "stress", "stress.png");
  const trainingImage = path.join(dataset, "images", "raw", "training.png");
  execFileSync("python", [
    "-c",
    "from PIL import Image; import sys; Image.new('RGB',(100,100),'white').save(sys.argv[1]); Image.new('RGB',(100,100),'red').save(sys.argv[2]); Image.new('RGB',(100,100),'black').save(sys.argv[3])",
    coreImage,
    stressImage,
    trainingImage,
  ]);

  const items: FrozenItem[] = [];
  for (const [lane, fileName, sourceGroup, parentSourceGroup] of [
    ["core", "core.png", "release-core", "release-parent-core"],
    ["stress", "stress.png", "release-stress", "release-parent-stress"],
  ] as const) {
    const imagePath = path.join(snapshot, "images", lane, fileName);
    const annotation = {
      version: "nail-texture-dataset/v1",
      image: {
        id: path.parse(fileName).name,
        fileName,
        width: 100,
        height: 100,
        sourceGroup,
        negative: false,
      },
      annotations: [{
        id: "n1",
        label: "nail_texture",
        polygon: [{ x: 10, y: 10 }, { x: 40, y: 10 }, { x: 30, y: 40 }],
      }],
    };
    const annotationPath = path.join(snapshot, "annotations", lane, `${path.parse(fileName).name}.json`);
    writeFileSync(annotationPath, JSON.stringify(annotation));
    const imageSha256 = sha(readFileSync(imagePath));
    const annotationSha256 = sha(readFileSync(annotationPath));
    items.push({
      lane,
      fileName,
      parentFileName: fileName,
      sourceGroup,
      parentSourceGroup,
      imageSha256,
      annotationSha256,
      imageAnnotationPairSha256: sha(canonical({ imageSha256, annotationSha256 })),
      width: 100,
      height: 100,
      maskCount: 1,
      authorizedUses: ["independent-release-test"],
      trainingUse: "prohibited",
    });
  }
  writeManifest(snapshot, items);
  writeFileSync(sources, [
    "imageId,fileName,sourceGroup,imagePath",
    "training,training.png,training-group,images/raw/training.png",
  ].join("\n"));
  const args = [
    script,
    "--snapshot-root", snapshot,
    "--output-dir", output,
    "--training-dataset-root", dataset,
    "--training-sources", sources,
  ];
  return { root, snapshot, output, report, dataset, sources, items, args };
}

function verifyArgs(item: ReturnType<typeof fixture>, expectedDataset = path.join(item.output, "dataset.yaml")) {
  return [script, "--verify-report", item.report, "--expected-dataset", expectedDataset];
}

test("materializes and deeply verifies a hash-bound core/stress evaluation-only dataset", () => {
  const item = fixture();
  execFileSync("python", item.args, { stdio: "pipe" });
  const report = JSON.parse(readFileSync(item.report, "utf8"));
  const manifest = JSON.parse(readFileSync(path.join(item.output, "evaluation-manifest.json"), "utf8"));
  assert.equal(report.schemaVersion, 2);
  assert.equal(report.ok, true);
  assert.equal(report.status, "PASS");
  assert.deepEqual(report.counts, {
    images: 2,
    masks: 2,
    coreImages: 1,
    stressImages: 1,
    trainImages: 0,
    validationImages: 0,
    testImages: 2,
    parentSourceGroups: 2,
  });
  assert.equal(report.inputs.sourceFrozenManifest.path, path.join(item.snapshot, "manifest.json"));
  assert.equal(report.inputs.sourceFrozenManifest.sha256, sha(readFileSync(path.join(item.snapshot, "manifest.json"))));
  assert.equal(report.inputs.sourceFrozenManifest.itemsSha256, report.sourceItemsSha256);
  assert.equal(report.artifacts.datasetYaml.path, path.join(item.output, "dataset.yaml"));
  assert.equal(report.artifacts.datasetYaml.sha256, sha(readFileSync(path.join(item.output, "dataset.yaml"))));
  assert.equal(report.artifacts.evaluationManifest.sha256, sha(readFileSync(path.join(item.output, "evaluation-manifest.json"))));
  assert.deepEqual(report.sourceIsolation.sourceGroupOverlap, []);
  assert.deepEqual(report.sourceIsolation.parentSourceGroupOverlap, []);
  assert.deepEqual(report.sourceIsolation.exactImageHashOverlap, []);
  assert.deepEqual(report.sourceIsolation.fileNameOverlap, []);
  assert.deepEqual(report.file_records.map((record: { path: string }) => record.path), listFiles(item.output));
  assert.deepEqual(report.datasetFiles, report.file_records);
  assert.equal(report.files_sha256, sha(canonical(report.file_records)));
  assert.equal(report.datasetFilesSha256, report.files_sha256);
  assert.deepEqual(manifest.records, report.records);
  assert.equal(manifest.recordsSha256, report.recordsSha256);
  for (const record of report.records) {
    assert.equal(record.materializedImageSha256, record.sourceImageSha256);
    assert.equal(record.materializedImageSha256, sha(readFileSync(path.join(item.output, record.materializedImage))));
    assert.equal(record.materializedLabelSha256, sha(readFileSync(path.join(item.output, record.materializedLabel))));
  }
  assert.deepEqual(listFiles(path.join(item.output, "images", "train")), []);
  assert.deepEqual(listFiles(path.join(item.output, "images", "val")), []);
  assert.deepEqual(listFiles(path.join(item.output, "labels", "train")), []);
  assert.deepEqual(listFiles(path.join(item.output, "labels", "val")), []);
  assert.deepEqual(listFiles(path.join(item.output, "images", "test")), ["core/core.png", "stress/stress.png"]);

  const verified = JSON.parse(execFileSync("python", verifyArgs(item), { encoding: "utf8" }));
  assert.equal(verified.ok, true);
  assert.equal(verified.outputWritten, false);
  assert.equal(verified.reportSha256, sha(readFileSync(item.report)));
  assert.equal(verified.datasetYamlSha256, report.artifacts.datasetYaml.sha256);
  assert.equal(verified.evaluationManifestSha256, report.artifacts.evaluationManifest.sha256);
  assert.equal(verified.sourceItemsSha256, report.sourceItemsSha256);
  assert.equal(verified.filesSha256, report.files_sha256);
});

test("rejects training identity overlap and leaves no partial output/report", () => {
  const item = fixture();
  const frozenImage = path.join(item.snapshot, "images", "core", "core.png");
  const trainingImage = path.join(item.dataset, "images", "raw", "training.png");
  writeFileSync(trainingImage, readFileSync(frozenImage));
  const result = spawnSync("python", item.args, { encoding: "utf8" });
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /identity overlaps training data/);
  assert.equal(existsSync(item.output), false);
  assert.equal(existsSync(item.report), false);
});

test("rejects any positive polygon overlap before writing targets", () => {
  const item = fixture();
  const annotationPath = path.join(item.snapshot, "annotations", "core", "core.json");
  const annotation = JSON.parse(readFileSync(annotationPath, "utf8"));
  annotation.annotations.push({
    id: "n2",
    label: "nail_texture",
    polygon: [{ x: 39.999, y: 10 }, { x: 60, y: 10 }, { x: 50, y: 40 }],
  });
  writeFileSync(annotationPath, JSON.stringify(annotation));
  const annotationSha256 = sha(readFileSync(annotationPath));
  item.items[0].annotationSha256 = annotationSha256;
  item.items[0].imageAnnotationPairSha256 = sha(canonical({
    imageSha256: item.items[0].imageSha256,
    annotationSha256,
  }));
  item.items[0].maskCount = 2;
  writeManifest(item.snapshot, item.items);
  const result = spawnSync("python", item.args, { encoding: "utf8" });
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /overlap by/);
  assert.equal(existsSync(item.output), false);
  assert.equal(existsSync(item.report), false);
});

test("rejects reused or source-nested output targets", async (t) => {
  await t.test("existing output", () => {
    const item = fixture();
    mkdirSync(item.output);
    const result = spawnSync("python", item.args, { encoding: "utf8" });
    assert.notEqual(result.status, 0);
    assert.match(result.stderr, /must not already exist/);
  });
  await t.test("output inside snapshot", () => {
    const item = fixture();
    const nested = path.join(item.snapshot, "derived-evaluation");
    const args = item.args.map((value, index, values) => values[index - 1] === "--output-dir" ? nested : value);
    const result = spawnSync("python", args, { encoding: "utf8" });
    assert.notEqual(result.status, 0);
    assert.match(result.stderr, /separate from the source snapshot/);
    assert.equal(existsSync(nested), false);
  });
});

test("deep verifier rejects forged PASS evidence, file drift, and dataset mismatch", async (t) => {
  await t.test("forged report aggregate", () => {
    const item = fixture();
    execFileSync("python", item.args, { stdio: "pipe" });
    const report = JSON.parse(readFileSync(item.report, "utf8"));
    report.files_sha256 = "0".repeat(64);
    writeFileSync(item.report, JSON.stringify(report));
    const result = spawnSync("python", verifyArgs(item), { encoding: "utf8" });
    assert.notEqual(result.status, 0);
    assert.match(result.stderr, /inventory or aggregate SHA-256 drift/);
  });
  await t.test("materialized label drift", () => {
    const item = fixture();
    execFileSync("python", item.args, { stdio: "pipe" });
    writeFileSync(path.join(item.output, "labels", "test", "core", "core.txt"), "0 0 0 1 1\n");
    const result = spawnSync("python", verifyArgs(item), { encoding: "utf8" });
    assert.notEqual(result.status, 0);
    assert.match(result.stderr, /label content drift/);
  });
  await t.test("expected dataset mismatch", () => {
    const item = fixture();
    execFileSync("python", item.args, { stdio: "pipe" });
    const result = spawnSync("python", verifyArgs(item, path.join(item.output, "dataset.core.yaml")), { encoding: "utf8" });
    assert.notEqual(result.status, 0);
    assert.match(result.stderr, /Expected dataset mismatch/);
  });
});
