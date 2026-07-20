import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { spawnSync } from "node:child_process";
import { mkdir, mkdtemp, readFile, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";

const script = path.resolve("model/training/calibrate-model-score-threshold.py");
const hash = (content: string | Buffer) => createHash("sha256").update(content).digest("hex");

function canonicalJson(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(",")}]`;
  if (value && typeof value === "object") {
    return `{${Object.entries(value as Record<string, unknown>)
      .sort(([left], [right]) => left.localeCompare(right))
      .map(([key, item]) => `${JSON.stringify(key)}:${canonicalJson(item)}`)
      .join(",")}}`;
  }
  return JSON.stringify(value) ?? "null";
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

async function buildCanonicalFixture() {
  const root = await mkdtemp(path.join(tmpdir(), "canonical-score-threshold-"));
  const sourceRoot = path.join(root, "source");
  const finalRoot = path.join(root, "validation-final");
  await mkdir(sourceRoot, { recursive: true });
  await mkdir(finalRoot, { recursive: true });
  const canonicalTruths: Array<Record<string, unknown>> = [];
  for (let index = 0; index < 30; index += 1) {
    const stem = `canonical-${String(index).padStart(3, "0")}`;
    const fileName = `${stem}.jpg`;
    const sourceGroup = `canonical-val-group-${String(index).padStart(3, "0")}`;
    const imagePath = path.join(sourceRoot, fileName);
    const annotationPath = path.join(sourceRoot, `${stem}.json`);
    const pixels = Array.from({ length: 100 }, (_, pixel) =>
      `${(index + pixel) % 256} ${(index * 3 + pixel) % 256} ${(index * 7 + pixel) % 256}`
    ).join(" ");
    await writeFile(imagePath, `P3\n10 10\n255\n${pixels}\n`);
    const annotation = {
      image: { fileName, sourceGroup, width: 10, height: 10 },
      annotations: [{
        label: "nail_texture",
        polygon: [{ x: 1, y: 1 }, { x: 8, y: 1 }, { x: 8, y: 8 }, { x: 1, y: 8 }],
      }],
    };
    await writeJson(annotationPath, annotation);
    const imageSha256 = hash(await readFile(imagePath));
    const annotationSha256 = hash(await readFile(annotationPath));
    const finalPath = path.join(finalRoot, `validation-truth-${String(index + 1).padStart(3, "0")}-final.json`);
    await writeJson(finalPath, {
      ok: true,
      decision: "approved_as_validation_truth_candidate_pending_dataset_materialization",
      inputs: {
        truthRole: "val",
        image: imagePath,
        imageSha256,
        annotation: annotationPath,
        annotationSha256,
      },
      item: {
        fileName,
        sha256: imageSha256,
        sourceGroup,
        completeMaskCount: 1,
        trainingUse: "prohibited",
      },
    });
    canonicalTruths.push({
      reportPath: finalPath,
      reportName: path.basename(finalPath),
      reportSha256: hash(await readFile(finalPath)),
      sequence: index + 1,
      fileName,
      imageSha256,
      sourceGroup,
      completeMaskCount: 1,
      annotationPath,
      annotationSha256,
    });
  }
  const truthIndex = path.join(root, "validation-truth-index.json");
  await writeJson(truthIndex, {
    schemaVersion: 1,
    ok: true,
    decision: "approved_unique_validation_truth_index",
    inputs: { truthRole: "val", truthDir: finalRoot, reportPattern: "validation-truth-*-final.json" },
    summary: {
      approvedReportCount: 30,
      rejectedReportCount: 0,
      uniqueImageCount: 30,
      completeMaskCount: 30,
      redundantReportCount: 0,
      redundantImageCount: 0,
      conflictingImageCount: 0,
    },
    canonicalTruths,
    errors: [],
    conflicts: [],
  });

  const datasetRoot = path.join(root, "canonical-validation-dataset");
  runPython([
    path.resolve("model/training/materialize-canonical-validation-dataset.py"),
    "--truth-index", truthIndex,
    "--output-dir", datasetRoot,
  ]);
  const dataset = path.join(datasetRoot, "dataset.yaml");
  const datasetReport = path.join(datasetRoot, "metadata", "materialization-report.json");

  const trainRoot = path.join(root, "train-role");
  await mkdir(trainRoot, { recursive: true });
  const trainImage = path.join(trainRoot, "train-only.jpg");
  await writeFile(trainImage, "P3\n2 2\n255\n1 2 3 4 5 6 7 8 9 10 11 12\n");
  const trainHash = hash(await readFile(trainImage));
  const trainFinal = path.join(trainRoot, "training-truth-001-final.json");
  await writeJson(trainFinal, {
    ok: true,
    decision: "approved_as_training_truth_candidate_pending_dataset_materialization",
    inputs: { truthRole: "train", image: trainImage, imageSha256: trainHash },
    item: {
      fileName: path.basename(trainImage), sha256: trainHash,
      sourceGroup: "train-only-group", trainingUse: "prohibited",
    },
  });
  const trainIndex = path.join(trainRoot, "training-truth-index.json");
  await writeJson(trainIndex, {
    ok: true,
    decision: "approved_unique_training_truth_index",
    inputs: { truthRole: "train" },
    summary: { uniqueImageCount: 1 },
    canonicalTruths: [{
      fileName: path.basename(trainImage), imageSha256: trainHash,
      sourceGroup: "train-only-group", reportPath: trainFinal,
      reportSha256: hash(await readFile(trainFinal)),
    }],
    errors: [], conflicts: [],
  });

  const frozenRoot = path.join(root, "frozen-role");
  await mkdir(path.join(frozenRoot, "images", "core"), { recursive: true });
  const frozenImage = path.join(frozenRoot, "images", "core", "frozen-only.jpg");
  await writeFile(frozenImage, "P3\n2 2\n255\n12 11 10 9 8 7 6 5 4 3 2 1\n");
  const frozenItem = {
    fileName: path.basename(frozenImage), imageSha256: hash(await readFile(frozenImage)),
    sourceGroup: "frozen-only-group", lane: "core", trainingUse: "prohibited",
  };
  const frozenManifest = path.join(frozenRoot, "manifest.json");
  await writeJson(frozenManifest, {
    decision: "frozen_reviewed_candidate_not_release_ready",
    trainingUse: "prohibited",
    counts: { images: 1 },
    itemsSha256: canonicalSha([frozenItem]),
    items: [frozenItem],
  });

  const roleIsolation = path.join(root, "validation-role-isolation.json");
  runPython([
    path.resolve("model/training/audit-validation-role-isolation.py"),
    "--val-materialization-report", datasetReport,
    "--train-truth-index", trainIndex,
    "--frozen-test-manifest", frozenManifest,
    "--output", roleIsolation,
  ]);
  const truthAudit = path.join(root, "validation-calibration-truth-audit.json");
  runPython([
    path.resolve("model/training/finalize-validation-materialization-audit.py"),
    "--dataset", dataset,
    "--truth-index", truthIndex,
    "--materialization-report", datasetReport,
    "--role-isolation-report", roleIsolation,
    "--output", truthAudit,
  ]);

  const artifacts = path.join(root, "evaluation-artifacts");
  const predictionRoot = path.join(artifacts, "labels");
  await mkdir(predictionRoot, { recursive: true });
  const fileRecords: Array<{ path: string; sha256: string }> = [];
  const predictionRecords: Array<Record<string, unknown>> = [];
  for (let index = 0; index < 30; index += 1) {
    const stem = `canonical-${String(index).padStart(3, "0")}`;
    const relative = `labels/${stem}.txt`;
    const predictionPath = path.join(artifacts, relative);
    await writeFile(predictionPath, "0 0.10000000 0.10000000 0.80000000 0.10000000 0.80000000 0.80000000 0.10000000 0.80000000 0.80\n");
    const predictionHash = hash(await readFile(predictionPath));
    fileRecords.push({ path: relative, sha256: predictionHash });
    predictionRecords.push({ stem, path: relative, sha256: predictionHash, prediction_count: 1 });
  }
  const artifactIndex = path.join(artifacts, "evaluation-artifacts.json");
  const artifactDocument = {
    schema_version: 1,
    split: "val",
    artifacts_dir: artifacts,
    files: fileRecords.map((item) => item.path),
    file_records: fileRecords,
    files_sha256: canonicalSha(fileRecords),
    prediction_records: predictionRecords,
    prediction_records_sha256: canonicalSha(predictionRecords),
    counts: { total: 30, plots: 0, prediction_labels: 30, json: 0 },
  };
  await writeJson(artifactIndex, artifactDocument);
  const weights = path.join(root, "best.pt");
  await writeFile(weights, "canonical-weights");
  const metrics = path.join(root, "val-metrics.json");
  await writeJson(metrics, {
    split: "val",
    dataset_yaml: dataset,
    dataset_yaml_sha256: hash(await readFile(dataset)),
    dataset_root: datasetRoot,
    weights,
    weights_sha256: hash(await readFile(weights)),
    evaluation_artifacts: {
      index: artifactIndex,
      index_sha256: hash(await readFile(artifactIndex)),
      files_sha256: artifactDocument.files_sha256,
    },
  });
  return {
    root, datasetRoot, dataset, datasetReport, truthIndex, trainIndex,
    frozenManifest, roleIsolation, truthAudit, artifacts, artifactIndex, metrics, weights,
  };
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

function runCanonicalCalibration(
  fixture: Awaited<ReturnType<typeof buildCanonicalFixture>>,
  output: string,
  extra: string[] = []
) {
  return spawnSync(
    "python",
    [
      script,
      "--dataset", fixture.dataset,
      "--dataset-report", fixture.datasetReport,
      "--metrics", fixture.metrics,
      "--truth-audit", fixture.truthAudit,
      "--output", output,
      "--confidence-sweep", "0.50,0.80,0.90",
      "--min-recall", "0.90",
      "--max-false-positives-per-image", "0.50",
      ...extra,
    ],
    { encoding: "utf8" }
  );
}

test("keeps a legacy source-isolated experiment diagnostic-only", async () => {
  const fixture = await buildFixture();
  const output = path.join(fixture.root, "calibration.json");
  const result = runCalibration(fixture, output);
  assert.equal(result.status, 0, result.stderr);
  const report = JSON.parse(await readFile(output, "utf8"));
  assert.equal(report.decision, "diagnostic_only_legacy_experiment_dataset");
  assert.equal(report.calibrationEligible, false);
  assert.equal(report.manifestScoreThreshold, null);
  assert.equal(report.diagnosticBestThreshold, 0.6);
  assert.equal(report.counts.validationImages, 2);
  assert.deepEqual(report.inputs.validationSourceGroups, ["validation"]);
  assert.equal(report.selected.falsePositives, 0);
  assert.equal(report.selected.recallAtIou50, 1);
  assert.match(report.releaseTestPolicy, /validation-only/);
});

test("calibrates a formal threshold from a deeply replayed canonical validation contract", async () => {
  const fixture = await buildCanonicalFixture();
  const output = path.join(fixture.root, "calibration.json");
  const result = runCanonicalCalibration(fixture, output);
  assert.equal(result.status, 0, result.stderr);
  const report = JSON.parse(await readFile(output, "utf8"));
  assert.equal(report.decision, "calibrated_threshold_ready_for_candidate_manifest");
  assert.equal(report.calibrationEligible, true);
  assert.equal(report.manifestScoreThreshold, 0.8);
  assert.equal(report.inputs.evidenceMode, "canonical-validation");
  assert.equal(report.counts.validationImages, 30);
  assert.equal(report.counts.truthMasks, 30);
  assert.equal(report.counts.predictionLabelFiles, 30);
});

test("rejects a forged canonical truth-audit PASS", async () => {
  const fixture = await buildCanonicalFixture();
  const audit = JSON.parse(await readFile(fixture.truthAudit, "utf8"));
  audit.counts.validationMasks += 1;
  await writeJson(fixture.truthAudit, audit);
  const result = runCanonicalCalibration(fixture, path.join(fixture.root, "calibration.json"));
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /differs from an independent replay/);
});

test("rejects canonical label hash drift", async () => {
  const fixture = await buildCanonicalFixture();
  const label = path.join(fixture.datasetRoot, "labels", "val", "canonical-000.txt");
  await writeFile(label, `${await readFile(label, "utf8")}\n`);
  const result = runCanonicalCalibration(fixture, path.join(fixture.root, "calibration.json"));
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /SHA-256 drift|hash drift/);
});

test("rejects canonical cross-role leakage even when the role report is rewritten", async () => {
  const fixture = await buildCanonicalFixture();
  const audit = JSON.parse(await readFile(fixture.truthAudit, "utf8"));
  const role = JSON.parse(await readFile(fixture.roleIsolation, "utf8"));
  const train = JSON.parse(await readFile(fixture.trainIndex, "utf8"));
  train.canonicalTruths[0].sourceGroup = audit.items[0].sourceGroup;
  const trainFinalPath = train.canonicalTruths[0].reportPath;
  const trainFinal = JSON.parse(await readFile(trainFinalPath, "utf8"));
  trainFinal.item.sourceGroup = audit.items[0].sourceGroup;
  await writeJson(trainFinalPath, trainFinal);
  train.canonicalTruths[0].reportSha256 = hash(await readFile(trainFinalPath));
  await writeJson(fixture.trainIndex, train);
  role.inputs.trainTruthIndex.sha256 = hash(await readFile(fixture.trainIndex));
  await writeJson(fixture.roleIsolation, role);
  audit.inputs.roleIsolationReportSha256 = hash(await readFile(fixture.roleIsolation));
  await writeJson(fixture.truthAudit, audit);
  const result = runCanonicalCalibration(fixture, path.join(fixture.root, "calibration.json"));
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /cross-role overlap/);
});

test("rejects formal artifact hash drift and unregistered prediction evidence", async () => {
  const fixture = await buildCanonicalFixture();
  const prediction = path.join(fixture.artifacts, "labels", "canonical-000.txt");
  await writeFile(prediction, `${await readFile(prediction, "utf8")}0 0.1 0.1 0.2 0.1 0.2 0.2 0.1 0.2 0.7\n`);
  const result = runCanonicalCalibration(fixture, path.join(fixture.root, "calibration.json"));
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /artifact hash drift|prediction label hash drift/);
});

test("rejects an orphan file in the formal artifact directory", async () => {
  const fixture = await buildCanonicalFixture();
  await writeFile(path.join(fixture.artifacts, "orphan.txt"), "stale-artifact");
  const result = runCanonicalCalibration(fixture, path.join(fixture.root, "calibration.json"));
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /missing or orphan files/);
});

test("rejects calibration output that overwrites an input", async () => {
  const fixture = await buildCanonicalFixture();
  const before = await readFile(fixture.dataset);
  const result = runCanonicalCalibration(fixture, fixture.dataset);
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /output must not overwrite/);
  assert.deepEqual(await readFile(fixture.dataset), before);
});

test("evaluation evidence records zero predictions explicitly", async () => {
  const root = await mkdtemp(path.join(tmpdir(), "evaluation-zero-prediction-"));
  const labels = path.join(root, "labels");
  await mkdir(labels, { recursive: true });
  await writeFile(path.join(labels, "has-prediction.txt"), "0 0.1 0.1 0.2 0.1 0.2 0.2 0.1 0.2 0.8\n");
  const python = [
    "import importlib.util,json,sys",
    "from pathlib import Path",
    "p=Path(sys.argv[1])",
    "sys.path.insert(0,str(Path(sys.argv[2]).parent))",
    "s=importlib.util.spec_from_file_location('evaluate_contract',sys.argv[2])",
    "m=importlib.util.module_from_spec(s);s.loader.exec_module(m)",
    "print(json.dumps(m.prediction_records(p,['has-prediction','zero-prediction'])))",
  ].join(";");
  const result = spawnSync("python", ["-c", python, root, path.resolve("model/training/evaluate.py")], { encoding: "utf8" });
  assert.equal(result.status, 0, result.stderr);
  const records = JSON.parse(result.stdout);
  assert.deepEqual(records[1], {
    stem: "zero-prediction", path: null, sha256: null, prediction_count: 0,
  });
});

test("evaluate rejects an empty split before loading Ultralytics", async () => {
  const root = await mkdtemp(path.join(tmpdir(), "evaluation-empty-split-"));
  for (const folder of ["images/train", "images/val", "images/test"]) {
    await mkdir(path.join(root, folder), { recursive: true });
  }
  const dataset = path.join(root, "dataset.yaml");
  await writeFile(dataset, [
    "path: .", "train: images/train", "val: images/val", "test: images/test", "",
    "names:", "  0: nail_texture", "", "task: segment", "class_count: 1", "image_size: 512", "",
  ].join("\n"));
  const weights = path.join(root, "best.pt");
  await writeFile(weights, "weights");
  const result = spawnSync("python", [
    path.resolve("model/training/evaluate.py"),
    "--dataset", dataset, "--weights", weights,
    "--output", path.join(root, "metrics.json"),
    "--artifacts-dir", path.join(root, "artifacts"),
    "--split", "val",
  ], { encoding: "utf8" });
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /no images/);
  assert.doesNotMatch(result.stderr, /ultralytics/i);
});

test("evaluate refuses to reuse an existing formal evidence output", async () => {
  const root = await mkdtemp(path.join(tmpdir(), "evaluation-output-reuse-"));
  const datasetRoot = path.join(root, "source-dataset");
  for (const folder of ["images/train", "images/val", "images/test"]) {
    await mkdir(path.join(datasetRoot, folder), { recursive: true });
  }
  await writeFile(path.join(datasetRoot, "images", "val", "sample.jpg"), "P3\n1 1\n255\n1 2 3\n");
  const dataset = path.join(datasetRoot, "dataset.yaml");
  await writeFile(dataset, [
    "path: .", "train: images/train", "val: images/val", "test: images/test", "",
    "names:", "  0: nail_texture", "", "task: segment", "class_count: 1", "image_size: 512", "",
  ].join("\n"));
  const weights = path.join(root, "best.pt");
  await writeFile(weights, "weights");
  const output = path.join(root, "metrics.json");
  await writeFile(output, "do-not-overwrite");
  const result = spawnSync("python", [
    path.resolve("model/training/evaluate.py"),
    "--dataset", dataset, "--weights", weights,
    "--output", output,
    "--artifacts-dir", path.join(root, "artifacts"),
    "--split", "val",
  ], { encoding: "utf8" });
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /must not already exist/);
  assert.equal(await readFile(output, "utf8"), "do-not-overwrite");
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

test("keeps repaired polygons in a legacy experiment diagnostic-only", async () => {
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
  assert.equal(report.decision, "diagnostic_only_legacy_experiment_dataset");
  assert.equal(report.calibrationEligible, false);
  assert.equal(report.manifestScoreThreshold, null);
  assert.equal(report.counts.repairedTruthPolygons, 1);
  assert.deepEqual(report.repairedTruthRecords, [{ fileName: "sample-a.txt", line: 1 }]);
});

test("keeps an unreviewed legacy validation split diagnostic-only", async () => {
  const fixture = await buildFixture();
  const output = path.join(fixture.root, "calibration.json");
  const result = runCalibration(fixture, output, ["--truth-audit", ""]);
  assert.equal(result.status, 0, result.stderr);
  const report = JSON.parse(await readFile(output, "utf8"));
  assert.equal(report.decision, "diagnostic_only_legacy_experiment_dataset");
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
