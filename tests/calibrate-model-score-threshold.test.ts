import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { spawnSync } from "node:child_process";
import { mkdir, mkdtemp, readFile, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";

const script = path.resolve("model/training/calibrate-model-score-threshold.py");
const hash = (content: string | Buffer) => createHash("sha256").update(content).digest("hex");
const canonicalHash = (value: unknown) => hash(JSON.stringify(value, Object.keys(value as object).sort()));

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

const canonicalSha = (value: unknown) => hash(canonicalJson(value));

async function writeJson(filePath: string, value: unknown) {
  await mkdir(path.dirname(filePath), { recursive: true });
  await writeFile(filePath, `${JSON.stringify(value, null, 2)}\n`);
}

function runPython(args: string[]) {
  const result = spawnSync("python", args, { encoding: "utf8" });
  assert.equal(result.status, 0, result.stderr || result.stdout);
}

async function buildFixture() {
  const root = await mkdtemp(path.join(tmpdir(), "score-threshold-calibration-"));
  const labels = path.join(root, "labels", "val");
  const images = path.join(root, "images", "val");
  const artifacts = path.join(root, "artifacts");
  const predictions = path.join(artifacts, "labels");
  await mkdir(labels, { recursive: true });
  await mkdir(images, { recursive: true });
  await mkdir(predictions, { recursive: true });

  const polygon = "0 0.10 0.10 0.30 0.10 0.30 0.30 0.10 0.30";
  await writeFile(path.join(labels, "sample-a.txt"), `${polygon}\n`);
  await writeFile(path.join(labels, "sample-b.txt"), `${polygon}\n`);
  await writeFile(path.join(images, "sample-a.jpg"), "a");
  await writeFile(path.join(images, "sample-b.jpg"), "b");
  await writeFile(
    path.join(predictions, "sample-a.txt"),
    [
      `${polygon} 0.80`,
      "0 0.60 0.60 0.75 0.60 0.75 0.75 0.60 0.75 0.40",
    ].join("\n") + "\n"
  );
  await writeFile(
    path.join(predictions, "sample-b.txt"),
    [
      `${polygon} 0.60`,
      "0 0.60 0.60 0.75 0.60 0.75 0.75 0.60 0.75 0.55",
    ].join("\n") + "\n"
  );

  const dataset = path.join(root, "dataset.yaml");
  await writeFile(
    dataset,
    [
      "path: .",
      "train: images/train",
      "val: images/val",
      "test: images/test",
      "",
      "names:",
      "  0: nail_texture",
      "",
      "task: segment",
      "class_count: 1",
      "image_size: 512",
      "",
    ].join("\n")
  );
  const datasetReport = path.join(root, "source-isolated-report.json");
  await writeFile(
    datasetReport,
    JSON.stringify({
      ok: true,
      decision: "experiment_only_source_isolated_real_dataset",
      outputDir: root,
      splitCounts: { train: 1, val: 2, test: 1 },
      groupCounts: {
        train: { train: 1, val: 0, test: 0 },
        validation: { train: 0, val: 2, test: 0 },
        test: { train: 0, val: 0, test: 1 },
      },
    })
  );
  const artifactIndex = path.join(artifacts, "evaluation-artifacts.json");
  await writeFile(
    artifactIndex,
    JSON.stringify({ split: "val", counts: { prediction_labels: 2 } })
  );
  const weights = path.join(root, "best.pt");
  await writeFile(weights, "weights");
  const metrics = path.join(root, "val-metrics.json");
  await writeFile(
    metrics,
    JSON.stringify({
      split: "val",
      dataset_root: root,
      weights,
      evaluation_artifacts: { index: artifactIndex },
    })
  );
  const truthAudit = path.join(root, "truth-audit.json");
  const datasetContent = await readFile(dataset);
  await writeFile(truthAudit, JSON.stringify({
    ok: true,
    decision: "approved_as_calibration_truth",
    calibrationTruthEligible: true,
    inputs: { split: "val", datasetYaml: dataset, datasetYamlSha256: hash(datasetContent) },
    counts: { expectedImages: 2, reviewedImages: 2, pass: 2, rework: 0, exclude: 0 },
    labelSha256: {
      "sample-a.txt": hash(await readFile(path.join(labels, "sample-a.txt"))),
      "sample-b.txt": hash(await readFile(path.join(labels, "sample-b.txt"))),
    },
  }));
  return { root, dataset, datasetReport, metrics, artifactIndex, truthAudit };
}

function runCalibration(
  fixture: Awaited<ReturnType<typeof buildFixture>>,
  output: string,
  extra: string[] = []
) {
  return spawnSync(
    "python",
    [
      script,
      "--dataset",
      fixture.dataset,
      "--dataset-report",
      fixture.datasetReport,
      "--metrics",
      fixture.metrics,
      "--truth-audit",
      fixture.truthAudit,
      "--output",
      output,
      "--confidence-sweep",
      "0.50,0.60,0.70",
      "--min-validation-images",
      "2",
      "--min-recall",
      "0.90",
      "--max-false-positives-per-image",
      "0.50",
      ...extra,
    ],
    { encoding: "utf8" }
  );
}

test("calibrates a manifest threshold from source-isolated validation predictions", async () => {
  const fixture = await buildFixture();
  const output = path.join(fixture.root, "calibration.json");
  const result = runCalibration(fixture, output);
  assert.equal(result.status, 0, result.stderr);
  const report = JSON.parse(await readFile(output, "utf8"));
  assert.equal(report.decision, "calibrated_threshold_ready_for_candidate_manifest");
  assert.equal(report.calibrationEligible, true);
  assert.equal(report.manifestScoreThreshold, 0.6);
  assert.deepEqual(report.inputs.validationSourceGroups, ["validation"]);
  assert.equal(report.selected.falsePositives, 0);
  assert.equal(report.selected.recallAtIou50, 1);
  assert.match(report.releaseTestPolicy, /validation-only/);
});

test("rejects validation source groups that leak into training", async () => {
  const fixture = await buildFixture();
  const report = JSON.parse(await readFile(fixture.datasetReport, "utf8"));
  report.groupCounts.validation.train = 1;
  await writeFile(fixture.datasetReport, JSON.stringify(report));
  const result = runCalibration(fixture, path.join(fixture.root, "calibration.json"));
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /validation source group leaks into train or test/);
});

test("rejects test predictions as threshold calibration evidence", async () => {
  const fixture = await buildFixture();
  const metrics = JSON.parse(await readFile(fixture.metrics, "utf8"));
  metrics.split = "test";
  await writeFile(fixture.metrics, JSON.stringify(metrics));
  const result = runCalibration(fixture, path.join(fixture.root, "calibration.json"));
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /requires metrics from split=val/);
});

test("keeps repaired validation polygons diagnostic-only", async () => {
  const fixture = await buildFixture();
  await writeFile(
    path.join(fixture.root, "labels", "val", "sample-a.txt"),
    "0 0.10 0.10 0.30 0.30 0.10 0.30 0.30 0.10\n"
  );
  const audit = JSON.parse(await readFile(fixture.truthAudit, "utf8"));
  audit.labelSha256["sample-a.txt"] = hash(await readFile(path.join(fixture.root, "labels", "val", "sample-a.txt")));
  await writeFile(fixture.truthAudit, JSON.stringify(audit));
  const output = path.join(fixture.root, "calibration.json");
  const result = runCalibration(fixture, output);
  assert.equal(result.status, 0, result.stderr);
  const report = JSON.parse(await readFile(output, "utf8"));
  assert.equal(report.decision, "diagnostic_only_validation_truth_requires_repair");
  assert.equal(report.calibrationEligible, false);
  assert.equal(report.manifestScoreThreshold, null);
  assert.equal(report.counts.repairedTruthPolygons, 1);
  assert.deepEqual(report.repairedTruthRecords, [{ fileName: "sample-a.txt", line: 1 }]);
});

test("keeps an unreviewed validation split diagnostic-only", async () => {
  const fixture = await buildFixture();
  const output = path.join(fixture.root, "calibration.json");
  const result = runCalibration(fixture, output, ["--truth-audit", ""]);
  assert.equal(result.status, 0, result.stderr);
  const report = JSON.parse(await readFile(output, "utf8"));
  assert.equal(report.decision, "diagnostic_only_validation_truth_unreviewed");
  assert.equal(report.manifestScoreThreshold, null);
});

test("keeps explicitly rejected validation truth diagnostic-only", async () => {
  const fixture = await buildFixture();
  await writeFile(fixture.truthAudit, JSON.stringify({
    ok: true,
    decision: "rejected_as_calibration_truth",
    calibrationTruthEligible: false,
  }));
  const output = path.join(fixture.root, "calibration.json");
  const result = runCalibration(fixture, output);
  assert.equal(result.status, 0, result.stderr);
  const report = JSON.parse(await readFile(output, "utf8"));
  assert.equal(report.decision, "diagnostic_only_validation_truth_rejected");
  assert.equal(report.manifestScoreThreshold, null);
});
