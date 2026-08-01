import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { execFileSync, spawnSync } from "node:child_process";
import { mkdirSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";

const script = path.resolve("model/training/build-positive-recognition-quality-report.py");

function canonical(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  if (value && typeof value === "object") return `{${Object.entries(value as Record<string, unknown>).sort(([a], [b]) => a.localeCompare(b)).map(([key, item]) => `${JSON.stringify(key)}:${canonical(item)}`).join(",")}}`;
  return JSON.stringify(value);
}

function sha(value: string | Buffer | unknown): string {
  const payload = typeof value === "string" || Buffer.isBuffer(value) ? value : canonical(value);
  return createHash("sha256").update(payload).digest("hex");
}

function fixture() {
  const root = mkdtempSync(path.join(tmpdir(), "positive-recognition-"));
  const outputDir = path.join(root, "dataset");
  const artifactsDir = path.join(root, "artifacts");
  mkdirSync(path.join(outputDir, "labels", "test", "core"), { recursive: true });
  mkdirSync(path.join(artifactsDir, "labels"), { recursive: true });
  const polygon = "0 0.1 0.1 0.4 0.1 0.4 0.6 0.1 0.6";
  const prediction = `${polygon} 0.9\n`;
  const items = ["a", "b"].map((stem) => ({ fileName: `${stem}.jpg`, maskCount: 1, trainingUse: "prohibited" }));
  const snapshot = path.join(root, "snapshot.json");
  writeFileSync(snapshot, JSON.stringify({ trainingUse: "prohibited", itemsSha256: sha(items), items }));
  const records = ["a", "b"].map((stem) => {
    const truthPath = path.join(outputDir, "labels", "test", "core", `${stem}.txt`);
    writeFileSync(truthPath, `${polygon}\n`);
    return { lane: "core", materializedFileName: `${stem}.jpg`, materializedLabel: `labels/test/core/${stem}.txt`, materializedLabelSha256: sha(readFileSync(truthPath)) };
  });
  const materialization = path.join(root, "materialization.json");
  writeFileSync(materialization, JSON.stringify({
    decision: "evaluation_only_frozen_reviewed_snapshot",
    trainingUse: "prohibited",
    sourceFrozenManifest: snapshot,
    sourceFrozenManifestSha256: sha(readFileSync(snapshot)),
    sourceItemsSha256: sha(items),
    outputDir,
    recordsSha256: sha(records),
    records,
  }));
  const predictionRecords = ["a", "b"].map((stem) => {
    const predictionPath = path.join(artifactsDir, "labels", `${stem}.txt`);
    writeFileSync(predictionPath, prediction);
    return { stem, path: `labels/${stem}.txt`, sha256: sha(readFileSync(predictionPath)), prediction_count: 1 };
  });
  const artifactIndex = path.join(root, "artifacts.json");
  writeFileSync(artifactIndex, JSON.stringify({ split: "test", artifacts_dir: artifactsDir, prediction_records: predictionRecords, prediction_records_sha256: sha(predictionRecords) }));
  const weights = path.join(root, "best.pt");
  writeFileSync(weights, "weights");
  return { root, snapshot, materialization, artifactIndex, weights, artifactsDir };
}

test("逐实例正样本识别报告可构建并重放", () => {
  const value = fixture();
  const output = path.join(value.root, "report.json");
  execFileSync("python", [script, "--snapshot-manifest", value.snapshot, "--materialization-report", value.materialization, "--artifact-index", value.artifactIndex, "--weights", value.weights, "--score-threshold", "0.5", "--min-images", "2", "--output", output]);
  const report = JSON.parse(readFileSync(output, "utf8"));
  assert.equal(report.ok, true);
  assert.equal(report.summary.directlyExtractableImages, 2);
  execFileSync("python", [script, "--verify-report", output]);
});

test("漏甲会让识别强门保持HOLD", () => {
  const value = fixture();
  const predictionPath = path.join(value.artifactsDir, "labels", "b.txt");
  writeFileSync(predictionPath, "");
  const artifact = JSON.parse(readFileSync(value.artifactIndex, "utf8"));
  artifact.prediction_records[1].sha256 = sha(readFileSync(predictionPath));
  artifact.prediction_records[1].prediction_count = 0;
  artifact.prediction_records_sha256 = sha(artifact.prediction_records);
  writeFileSync(value.artifactIndex, JSON.stringify(artifact));
  const output = path.join(value.root, "hold.json");
  const result = spawnSync("python", [script, "--snapshot-manifest", value.snapshot, "--materialization-report", value.materialization, "--artifact-index", value.artifactIndex, "--weights", value.weights, "--score-threshold", "0.5", "--min-images", "2", "--output", output]);
  assert.equal(result.status, 1);
  const report = JSON.parse(readFileSync(output, "utf8"));
  assert.equal(report.decision, "hold_positive_recognition_gate");
  assert.equal(report.summary.missing, 1);
  assert.equal(report.gates.everyImageHasModelOutput, false);
  const verify = spawnSync("python", [script, "--verify-report", output]);
  assert.equal(verify.status, 1);
});

test("拓扑无效预测只用于诊断修复且必须HOLD", () => {
  const value = fixture();
  const predictionPath = path.join(value.artifactsDir, "labels", "b.txt");
  writeFileSync(predictionPath, "0 0.1 0.1 0.4 0.6 0.1 0.6 0.4 0.1 0.9\n");
  const artifact = JSON.parse(readFileSync(value.artifactIndex, "utf8"));
  artifact.prediction_records[1].sha256 = sha(readFileSync(predictionPath));
  artifact.prediction_records_sha256 = sha(artifact.prediction_records);
  writeFileSync(value.artifactIndex, JSON.stringify(artifact));
  const output = path.join(value.root, "invalid.json");
  const result = spawnSync("python", [script, "--snapshot-manifest", value.snapshot, "--materialization-report", value.materialization, "--artifact-index", value.artifactIndex, "--weights", value.weights, "--score-threshold", "0.5", "--min-images", "2", "--output", output]);
  assert.equal(result.status, 1);
  const report = JSON.parse(readFileSync(output, "utf8"));
  assert.equal(report.summary.invalidPredictionMasks, 1);
  assert.equal(report.gates.zeroInvalidPredictionMasks, false);
});
