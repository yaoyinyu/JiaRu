import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import {
  mkdirSync,
  mkdtempSync,
  readFileSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

const python = process.env.PYTHON ?? "python";
const materializer = path.resolve(
  "model/training/materialize-canonical-validation-dataset.py",
);
const isolationAuditor = path.resolve(
  "model/training/audit-validation-role-isolation.py",
);
const truthFinalizer = path.resolve(
  "model/training/finalize-validation-materialization-audit.py",
);
const calibrator = path.resolve(
  "model/training/calibrate-model-score-threshold.py",
);

const shaFile = (file: string) =>
  createHash("sha256").update(readFileSync(file)).digest("hex");

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

const canonicalSha = (value: unknown) =>
  createHash("sha256").update(canonicalJson(value)).digest("hex");

function writeJson(file: string, value: unknown) {
  mkdirSync(path.dirname(file), { recursive: true });
  writeFileSync(file, `${JSON.stringify(value, null, 2)}\n`);
}

function run(args: string[]) {
  const result = spawnSync(python, args, { encoding: "utf8" });
  if (result.status !== 0) {
    throw new Error(
      `formal threshold fixture command failed:\n${args.join(" ")}\n` +
        `${result.stderr || result.stdout}`,
    );
  }
}

export function createFormalThresholdEvidence(scoreThreshold = 0.45) {
  const root = mkdtempSync(path.join(tmpdir(), "formal-threshold-evidence-"));
  const sourceRoot = path.join(root, "source");
  const finalRoot = path.join(root, "validation-final");
  mkdirSync(sourceRoot, { recursive: true });
  mkdirSync(finalRoot, { recursive: true });
  const canonicalTruths: Array<Record<string, unknown>> = [];

  for (let index = 0; index < 30; index += 1) {
    const stem = `canonical-${String(index).padStart(3, "0")}`;
    const fileName = `${stem}.jpg`;
    const sourceGroup = `canonical-val-group-${String(index).padStart(3, "0")}`;
    const image = path.join(sourceRoot, fileName);
    const annotation = path.join(sourceRoot, `${stem}.json`);
    const pixels = Array.from({ length: 100 }, (_, pixel) =>
      `${(index + pixel) % 256} ${(index * 3 + pixel) % 256} ${(index * 7 + pixel) % 256}`,
    ).join(" ");
    writeFileSync(image, `P3\n10 10\n255\n${pixels}\n`);
    writeJson(annotation, {
      image: { fileName, sourceGroup, width: 10, height: 10 },
      annotations: [
        {
          label: "nail_texture",
          polygon: [
            { x: 1, y: 1 },
            { x: 8, y: 1 },
            { x: 8, y: 8 },
            { x: 1, y: 8 },
          ],
        },
      ],
    });
    const imageSha256 = shaFile(image);
    const annotationSha256 = shaFile(annotation);
    const finalReport = path.join(
      finalRoot,
      `validation-truth-${String(index + 1).padStart(3, "0")}-final.json`,
    );
    writeJson(finalReport, {
      ok: true,
      decision:
        "approved_as_validation_truth_candidate_pending_dataset_materialization",
      inputs: {
        truthRole: "val",
        image,
        imageSha256,
        annotation,
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
      reportPath: finalReport,
      reportName: path.basename(finalReport),
      reportSha256: shaFile(finalReport),
      sequence: index + 1,
      fileName,
      imageSha256,
      sourceGroup,
      completeMaskCount: 1,
      annotationPath: annotation,
      annotationSha256,
    });
  }

  const truthIndex = path.join(root, "validation-truth-index.json");
  writeJson(truthIndex, {
    schemaVersion: 1,
    ok: true,
    decision: "approved_unique_validation_truth_index",
    inputs: {
      truthRole: "val",
      truthDir: finalRoot,
      reportPattern: "validation-truth-*-final.json",
    },
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
  run([
    materializer,
    "--truth-index",
    truthIndex,
    "--output-dir",
    datasetRoot,
  ]);
  const dataset = path.join(datasetRoot, "dataset.yaml");
  const datasetReport = path.join(
    datasetRoot,
    "metadata",
    "materialization-report.json",
  );

  const trainRoot = path.join(root, "train-role");
  mkdirSync(trainRoot, { recursive: true });
  const trainImage = path.join(trainRoot, "train-only.jpg");
  writeFileSync(
    trainImage,
    "P3\n2 2\n255\n1 2 3 4 5 6 7 8 9 10 11 12\n",
  );
  const trainFinal = path.join(trainRoot, "training-truth-001-final.json");
  writeJson(trainFinal, {
    ok: true,
    decision:
      "approved_as_training_truth_candidate_pending_dataset_materialization",
    inputs: {
      truthRole: "train",
      image: trainImage,
      imageSha256: shaFile(trainImage),
    },
    item: {
      fileName: path.basename(trainImage),
      sha256: shaFile(trainImage),
      sourceGroup: "train-only-group",
      trainingUse: "prohibited",
    },
  });
  const trainIndex = path.join(trainRoot, "training-truth-index.json");
  writeJson(trainIndex, {
    ok: true,
    decision: "approved_unique_training_truth_index",
    inputs: { truthRole: "train" },
    summary: { uniqueImageCount: 1 },
    canonicalTruths: [
      {
        fileName: path.basename(trainImage),
        imageSha256: shaFile(trainImage),
        sourceGroup: "train-only-group",
        reportPath: trainFinal,
        reportSha256: shaFile(trainFinal),
      },
    ],
    errors: [],
    conflicts: [],
  });

  const frozenRoot = path.join(root, "frozen-role");
  const frozenImage = path.join(frozenRoot, "images", "core", "frozen-only.jpg");
  mkdirSync(path.dirname(frozenImage), { recursive: true });
  writeFileSync(
    frozenImage,
    "P3\n2 2\n255\n12 11 10 9 8 7 6 5 4 3 2 1\n",
  );
  const frozenItem = {
    fileName: path.basename(frozenImage),
    imageSha256: shaFile(frozenImage),
    sourceGroup: "frozen-only-group",
    lane: "core",
    trainingUse: "prohibited",
  };
  const frozenManifest = path.join(frozenRoot, "manifest.json");
  writeJson(frozenManifest, {
    decision: "frozen_reviewed_candidate_not_release_ready",
    trainingUse: "prohibited",
    counts: { images: 1 },
    itemsSha256: canonicalSha([frozenItem]),
    items: [frozenItem],
  });

  const roleIsolation = path.join(root, "validation-role-isolation.json");
  run([
    isolationAuditor,
    "--val-materialization-report",
    datasetReport,
    "--train-truth-index",
    trainIndex,
    "--frozen-test-manifest",
    frozenManifest,
    "--output",
    roleIsolation,
  ]);
  const truthAudit = path.join(root, "validation-calibration-truth-audit.json");
  run([
    truthFinalizer,
    "--dataset",
    dataset,
    "--truth-index",
    truthIndex,
    "--materialization-report",
    datasetReport,
    "--role-isolation-report",
    roleIsolation,
    "--output",
    truthAudit,
  ]);

  const artifacts = path.join(root, "evaluation-artifacts");
  const predictionRoot = path.join(artifacts, "labels");
  mkdirSync(predictionRoot, { recursive: true });
  const fileRecords: Array<{ path: string; sha256: string }> = [];
  const predictionRecords: Array<Record<string, unknown>> = [];
  for (let index = 0; index < 30; index += 1) {
    const stem = `canonical-${String(index).padStart(3, "0")}`;
    const relative = `labels/${stem}.txt`;
    const prediction = path.join(artifacts, relative);
    writeFileSync(
      prediction,
      `0 0.10000000 0.10000000 0.80000000 0.10000000 0.80000000 0.80000000 0.10000000 0.80000000 ${scoreThreshold.toFixed(2)}\n`,
    );
    const predictionSha256 = shaFile(prediction);
    fileRecords.push({ path: relative, sha256: predictionSha256 });
    predictionRecords.push({
      stem,
      path: relative,
      sha256: predictionSha256,
      prediction_count: 1,
    });
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
  writeJson(artifactIndex, artifactDocument);

  const weights = path.join(root, "best.pt");
  writeFileSync(weights, "formal-threshold-fixture-weights");
  const metrics = path.join(root, "val-metrics.json");
  writeJson(metrics, {
    split: "val",
    dataset_yaml: dataset,
    dataset_yaml_sha256: shaFile(dataset),
    dataset_root: datasetRoot,
    weights,
    weights_sha256: shaFile(weights),
    evaluation_artifacts: {
      index: artifactIndex,
      index_sha256: shaFile(artifactIndex),
      files_sha256: artifactDocument.files_sha256,
    },
  });
  const thresholdReport = path.join(root, "score-threshold-calibration.json");
  run([
    calibrator,
    "--dataset",
    dataset,
    "--dataset-report",
    datasetReport,
    "--metrics",
    metrics,
    "--truth-audit",
    truthAudit,
    "--output",
    thresholdReport,
    "--confidence-sweep",
    `${scoreThreshold.toFixed(2)},0.80,0.90`,
    "--min-recall",
    "0.90",
    "--max-false-positives-per-image",
    "0.50",
  ]);
  const report = JSON.parse(readFileSync(thresholdReport, "utf8"));
  if (
    report.decision !==
      "calibrated_threshold_ready_for_candidate_manifest" ||
    report.manifestScoreThreshold !== scoreThreshold
  ) {
    throw new Error(
      `formal threshold fixture produced an unexpected decision: ${JSON.stringify({
        decision: report.decision,
        manifestScoreThreshold: report.manifestScoreThreshold,
      })}`,
    );
  }
  return { root, weights, thresholdReport, scoreThreshold };
}
