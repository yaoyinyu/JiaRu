import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { execFileSync, spawnSync } from "node:child_process";
import { mkdtempSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";

const script = path.resolve("model/training/materialize-frozen-release-test-evaluation.py");
const sha = (value: Buffer | string) => createHash("sha256").update(value).digest("hex");

function canonical(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  if (value && typeof value === "object") {
    return `{${Object.entries(value as Record<string, unknown>).sort(([a], [b]) => a.localeCompare(b)).map(([key, item]) => `${JSON.stringify(key)}:${canonical(item)}`).join(",")}}`;
  }
  return JSON.stringify(value);
}

function fixture() {
  const root = mkdtempSync(path.join(tmpdir(), "frozen-evaluation-"));
  const snapshot = path.join(root, "snapshot");
  const output = path.join(root, "evaluation");
  const dataset = path.join(root, "training");
  const sources = path.join(dataset, "metadata", "sources.csv");
  mkdirSync(path.join(snapshot, "images", "core"), { recursive: true });
  mkdirSync(path.join(snapshot, "annotations", "core"), { recursive: true });
  mkdirSync(path.join(dataset, "images", "raw"), { recursive: true });
  mkdirSync(path.dirname(sources), { recursive: true });
  const frozenImage = path.join(snapshot, "images", "core", "sample.png");
  const trainingImage = path.join(dataset, "images", "raw", "training.png");
  execFileSync("python", ["-c", "from PIL import Image; import sys; Image.new('RGB',(100,100),'white').save(sys.argv[1]); Image.new('RGB',(100,100),'black').save(sys.argv[2])", frozenImage, trainingImage]);
  const annotation = {
    version: "nail-texture-dataset/v1",
    image: { id: "sample", fileName: "sample.png", width: 100, height: 100, sourceGroup: "release-group", negative: false },
    annotations: [{ id: "n1", label: "nail_texture", polygon: [{ x: 10, y: 10 }, { x: 40, y: 10 }, { x: 30, y: 40 }] }],
  };
  const annotationPath = path.join(snapshot, "annotations", "core", "sample.json");
  writeFileSync(annotationPath, JSON.stringify(annotation));
  const imageHash = sha(readFileSync(frozenImage));
  const annotationHash = sha(readFileSync(annotationPath));
  const pair = { imageSha256: imageHash, annotationSha256: annotationHash };
  const items = [{
    lane: "core", fileName: "sample.png", parentFileName: "sample.png", sourceGroup: "release-group", parentSourceGroup: "release-parent",
    imageSha256: imageHash, annotationSha256: annotationHash, imageAnnotationPairSha256: sha(canonical(pair)),
    width: 100, height: 100, maskCount: 1, authorizedUses: ["independent-release-test"], trainingUse: "prohibited",
  }];
  writeFileSync(path.join(snapshot, "manifest.json"), JSON.stringify({
    snapshotId: "snapshot-v1", decision: "frozen_reviewed_candidate_not_release_ready", trainingUse: "prohibited",
    counts: { images: 1, masks: 1 }, itemsSha256: sha(canonical(items)), items,
  }));
  writeFileSync(sources, [
    "imageId,fileName,sourceGroup,imagePath",
    "training,training.png,training-group,images/raw/training.png",
  ].join("\n"));
  const args = [script, "--snapshot-root", snapshot, "--output-dir", output, "--training-dataset-root", dataset, "--training-sources", sources];
  return { root, snapshot, output, dataset, sources, args };
}

test("materializes a source-isolated frozen snapshot as evaluation-only YOLO data", () => {
  const item = fixture();
  execFileSync("python", item.args, { stdio: "pipe" });
  const report = JSON.parse(readFileSync(`${item.output}-report.json`, "utf8"));
  const manifest = JSON.parse(readFileSync(path.join(item.output, "evaluation-manifest.json"), "utf8"));
  assert.equal(report.ok, true);
  assert.deepEqual(report.counts, { images: 1, masks: 1, parentSourceGroups: 1 });
  assert.deepEqual(report.sourceIsolation.parentSourceGroupOverlap, []);
  assert.deepEqual(report.sourceIsolation.exactImageHashOverlap, []);
  assert.equal(manifest.trainingUse, "prohibited");
  assert.match(readFileSync(path.join(item.output, "dataset.yaml"), "utf8"), /train: images\/empty[\s\S]*test: images\/test/);
  assert.match(readFileSync(path.join(item.output, "dataset.core.yaml"), "utf8"), /test: images\/test\/core/);
  assert.match(readFileSync(path.join(item.output, "labels", "test", "core", "sample.txt"), "utf8"), /^0 0\.10000000/);
});

test("rejects a frozen image that duplicates formal training data", () => {
  const item = fixture();
  const frozenImage = path.join(item.snapshot, "images", "core", "sample.png");
  const trainingImage = path.join(item.dataset, "images", "raw", "training.png");
  writeFileSync(trainingImage, readFileSync(frozenImage));
  const result = spawnSync("python", item.args, { encoding: "utf8" });
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /exactly duplicates formal training data/);
});
