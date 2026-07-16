import assert from "node:assert/strict";
import { execFileSync, spawnSync } from "node:child_process";
import { mkdirSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";
import { createHash } from "node:crypto";

const script = path.resolve("model/training/build-validation-topology-repair-candidates.py");
const hash = (file: string) => createHash("sha256").update(readFileSync(file)).digest("hex");

function fixture() {
  const root = mkdtempSync(path.join(tmpdir(), "validation-topology-candidate-"));
  const dataset = path.join(root, "dataset");
  const images = path.join(dataset, "images", "val");
  const labels = path.join(dataset, "labels", "val");
  mkdirSync(images, { recursive: true });
  mkdirSync(labels, { recursive: true });
  execFileSync("python", ["-c", "from PIL import Image; import sys; Image.new('RGB',(100,100),'white').save(sys.argv[1])", path.join(images, "sample.jpg")]);
  writeFileSync(path.join(labels, "sample.txt"), "0 0.1 0.1 0.8 0.8 0.1 0.8 0.8 0.1\n");
  const datasetYaml = path.join(dataset, "dataset.yaml");
  writeFileSync(datasetYaml, `path: ${dataset.replaceAll("\\", "/")}\ntrain: images/train\nval: images/val\ntest: images/test\nnames:\n  0: nail_texture\ntask: segment\nclass_count: 1\nimage_size: 512\n`);
  const sourceReport = path.join(dataset, "source-report.json");
  writeFileSync(sourceReport, JSON.stringify({ decision: "experiment_only_source_isolated_real_dataset", outputDir: dataset }));
  const calibration = path.join(root, "calibration.json");
  writeFileSync(calibration, JSON.stringify({
    decision: "diagnostic_only_validation_truth_requires_repair",
    calibrationEligible: false,
    manifestScoreThreshold: null,
    inputs: { split: "val", datasetYaml, datasetYamlSha256: hash(datasetYaml), datasetReport: sourceReport, datasetReportSha256: hash(sourceReport) },
    counts: { repairedTruthPolygons: 1 },
    repairedTruthRecords: [{ fileName: "sample.txt", line: 1 }],
  }));
  return { root, datasetYaml, sourceReport, calibration, labels, output: path.join(root, "candidate-labels"), overlays: path.join(root, "overlays"), crops: path.join(root, "crops"), report: path.join(root, "report.json") };
}

function args(item: ReturnType<typeof fixture>) {
  return [script, "--dataset", item.datasetYaml, "--calibration-report", item.calibration, "--output-labels", item.output, "--overlay-dir", item.overlays, "--crop-dir", item.crops, "--report", item.report, "--maximum-discard-ratio", "0.10"];
}

test("builds isolated candidates and leaves source truth unchanged", () => {
  const item = fixture();
  const before = hash(path.join(item.labels, "sample.txt"));
  execFileSync("python", args(item));
  const report = JSON.parse(readFileSync(item.report, "utf8"));
  assert.equal(report.ok, true);
  assert.equal(report.decision, "candidate_only_requires_original_resolution_review");
  assert.equal(report.counts.repairedPolygons, 1);
  assert.equal(report.sourceLabelsUnmodified, true);
  assert.equal(hash(path.join(item.labels, "sample.txt")), before);
  assert.notEqual(hash(path.join(item.output, "sample.txt")), before);
});

test("rejects calibration evidence that is not validation-only", () => {
  const item = fixture();
  const calibration = JSON.parse(readFileSync(item.calibration, "utf8"));
  calibration.inputs.split = "test";
  writeFileSync(item.calibration, JSON.stringify(calibration));
  const result = spawnSync("python", args(item), { encoding: "utf8" });
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /split=val/);
});

test("rejects calibration whose bound dataset hash has drifted", () => {
  const item = fixture();
  writeFileSync(item.datasetYaml, readFileSync(item.datasetYaml, "utf8") + "image_size: 512\n");
  const result = spawnSync("python", args(item), { encoding: "utf8" });
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /dataset hash/);
});
