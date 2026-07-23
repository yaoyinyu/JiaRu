import assert from "node:assert/strict";
import { mkdir, mkdtemp, readFile, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import test from "node:test";
import { createHash } from "node:crypto";

const script = path.resolve("model/training/profile-frozen-release-test-failures.py");
const hash = (value: string) => createHash("sha256").update(value).digest("hex");
const canonical = (value: unknown): string => {
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  if (value && typeof value === "object") {
    return `{${Object.entries(value as Record<string, unknown>)
      .sort(([left], [right]) => left.localeCompare(right))
      .map(([key, item]) => `${JSON.stringify(key)}:${canonical(item)}`)
      .join(",")}}`;
  }
  return JSON.stringify(value);
};

async function fixture() {
  const root = await mkdtemp(path.join(tmpdir(), "frozen-failure-profile-"));
  const evaluation = path.join(root, "evaluation");
  const artifacts = path.join(root, "artifacts");
  await mkdir(path.join(evaluation, "labels", "test", "stress"), { recursive: true });
  await mkdir(path.join(artifacts, "labels"), { recursive: true });
  const truth = [
    "0 0.10 0.10 0.30 0.10 0.30 0.30 0.10 0.30",
    "0 0.60 0.60 0.80 0.60 0.80 0.80 0.60 0.80",
  ].join("\n") + "\n";
  await writeFile(path.join(evaluation, "labels", "test", "stress", "sample.txt"), truth);
  const prediction = [
    "0 0.10 0.10 0.30 0.10 0.30 0.30 0.10 0.30 0.90",
    "0 0.40 0.10 0.50 0.10 0.50 0.20 0.40 0.20 0.80",
  ].join("\n") + "\n";
  await writeFile(path.join(artifacts, "labels", "stress__sample.txt"), prediction);
  await writeFile(path.join(evaluation, "evaluation-manifest.json"), JSON.stringify({
    decision: "evaluation_only_frozen_reviewed_snapshot",
    trainingUse: "prohibited",
    sourceItemsSha256: "a".repeat(64),
    counts: { images: 1, masks: 2 },
    sourceIsolation: { parentSourceGroupOverlap: [], exactImageHashOverlap: [] },
    records: [{ lane: "stress", materializedFileName: "sample.jpg", parentSourceGroup: "test-only", maskCount: 2, materializedLabelSha256: hash(truth) }],
  }));
  const predictionRecords = [{
    stem: "stress__sample",
    path: "labels/stress__sample.txt",
    sha256: hash(prediction),
    prediction_count: 2,
  }];
  await writeFile(path.join(artifacts, "evaluation-artifacts.json"), JSON.stringify({
    split: "test",
    counts: { prediction_labels: 1 },
    prediction_records: predictionRecords,
    prediction_records_sha256: hash(canonical(predictionRecords)),
  }));
  return { root, evaluation, artifacts };
}

test("profiles matched, missed, and false-positive frozen instances without authorizing training", async () => {
  const { root, evaluation, artifacts } = await fixture();
  const output = path.join(root, "report.json");
  const result = spawnSync("python", [script, "--evaluation-root", evaluation, "--artifact-index", path.join(artifacts, "evaluation-artifacts.json"), "--output", output], { encoding: "utf8" });
  assert.equal(result.status, 0, result.stderr);
  const report = JSON.parse(await readFile(output, "utf8"));
  assert.equal(report.trainingUse, "prohibited");
  assert.equal(report.counts.matchedMasks, 1);
  assert.equal(report.counts.missedMasks, 1);
  assert.equal(report.counts.falsePositives, 1);
  assert.equal(report.byLane[0].lane, "stress");
  assert.equal(report.thresholdSweep.length, 6);
  assert.equal(report.thresholdSweep[0].confidence, 0.2);
  assert.match(report.trainingGuidance.prohibited, /frozen test image/);
});

test("rejects a frozen evaluation manifest that overlaps training sources", async () => {
  const { root, evaluation, artifacts } = await fixture();
  const manifestPath = path.join(evaluation, "evaluation-manifest.json");
  const manifest = JSON.parse(await readFile(manifestPath, "utf8"));
  manifest.sourceIsolation.parentSourceGroupOverlap = ["leaked-group"];
  await writeFile(manifestPath, JSON.stringify(manifest));
  const result = spawnSync("python", [script, "--evaluation-root", evaluation, "--artifact-index", path.join(artifacts, "evaluation-artifacts.json"), "--output", path.join(root, "report.json")], { encoding: "utf8" });
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /overlaps a formal training source group/);
});
