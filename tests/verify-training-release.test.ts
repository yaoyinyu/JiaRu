import assert from "node:assert/strict";
import { execFile } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdtemp, mkdir, readFile, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { promisify } from "node:util";
import test from "node:test";

const execFileAsync = promisify(execFile);
const sha256 = (value: string | Buffer) => createHash("sha256").update(value).digest("hex");

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

test("verify-training-release passes when metrics and manifest gates are satisfied", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-training-release-pass-"));
  const exportsDir = path.join(root, "model", "exports", "nail-texture-seg-v1");
  const modelDir = path.join(root, "public", "models", "nail-texture-seg");
  await mkdir(exportsDir, { recursive: true });
  await mkdir(modelDir, { recursive: true });

  await writeFile(
    path.join(exportsDir, "metrics.json"),
    JSON.stringify(
      {
        dataset_yaml: "model/training/dataset.yaml",
        dataset_root: "model/datasets/nail-texture-v1",
        weights: "model/exports/nail-texture-seg-v1/best.pt",
        output: "model/exports/nail-texture-seg-v1/metrics.json",
        split: "test",
        imgsz: 640,
        device: "auto",
        dry_run: false,
        box_map50: 0.9,
        box_map: 0.82,
        seg_map50: 0.8,
        seg_map: 0.71,
      },
      null,
      2
    ),
    "utf8"
  );
  await writeFile(
    path.join(modelDir, "manifest.json"),
    JSON.stringify(
      {
        version: "nail-texture-seg-v1",
        inputSize: 640,
        task: "segment",
        backendPreferences: ["webgpu", "wasm"],
        modelFile: "nail-texture-seg-v1.onnx",
        modelSizeBytes: 307200,
        sha256: "7818f5542a0404157573be6cffc0e0c8e68ce3c0f5d17d07ccdd9313fb700baf",
        labels: ["nail_texture"],
      },
      null,
      2
    ),
    "utf8"
  );
  await writeFile(path.join(modelDir, "nail-texture-seg-v1.onnx"), Buffer.alloc(300 * 1024), "binary");

  const { stdout } = await execFileAsync(
    process.execPath,
    [
      "--no-warnings",
      "--experimental-strip-types",
      "scripts/verify-training-release.ts",
      "--metrics",
      path.join(exportsDir, "metrics.json"),
      "--manifest",
      path.join(modelDir, "manifest.json"),
    ],
    {
      cwd: path.resolve("."),
    }
  );

  const summary = JSON.parse(stdout) as {
    ok: boolean;
    errors: string[];
    warnings: string[];
    metrics: { seg_map50: number };
    artifact: { modelExists: boolean };
  };
  assert.equal(summary.ok, true);
  assert.deepEqual(summary.errors, []);
  assert.equal(summary.metrics.seg_map50, 0.8);
  assert.equal(summary.artifact.modelExists, true);
});

test("verify-training-release fails on threshold and consistency mismatches", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-training-release-fail-"));
  const exportsDir = path.join(root, "model", "exports", "nail-texture-seg-v2");
  const modelDir = path.join(root, "public", "models", "nail-texture-seg");
  await mkdir(exportsDir, { recursive: true });
  await mkdir(modelDir, { recursive: true });

  await writeFile(
    path.join(exportsDir, "metrics.json"),
    JSON.stringify(
      {
        dataset_yaml: "model/training/dataset.yaml",
        dataset_root: "model/datasets/nail-texture-v1",
        weights: "model/exports/nail-texture-seg-v2/best.pt",
        output: "model/exports/nail-texture-seg-v2/metrics.json",
        split: "val",
        imgsz: 512,
        device: "auto",
        dry_run: false,
        box_map50: 0.7,
        box_map: 0.6,
        seg_map50: 0.6,
        seg_map: 0.5,
      },
      null,
      2
    ),
    "utf8"
  );
  await writeFile(
    path.join(modelDir, "manifest.json"),
    JSON.stringify(
      {
        version: "nail-texture-seg-v1",
        inputSize: 640,
        task: "segment",
        backendPreferences: ["webgpu", "wasm"],
        modelFile: "nail-texture-seg-v1.onnx",
        modelSizeBytes: 307200,
        sha256: "7818f5542a0404157573be6cffc0e0c8e68ce3c0f5d17d07ccdd9313fb700baf",
        labels: ["nail_texture"],
      },
      null,
      2
    ),
    "utf8"
  );
  await writeFile(path.join(modelDir, "nail-texture-seg-v1.onnx"), Buffer.alloc(300 * 1024), "binary");

  await assert.rejects(
    execFileAsync(
      process.execPath,
      [
        "--no-warnings",
        "--experimental-strip-types",
        "scripts/verify-training-release.ts",
        "--metrics",
        path.join(exportsDir, "metrics.json"),
        "--manifest",
        path.join(modelDir, "manifest.json"),
      ],
      {
        cwd: path.resolve("."),
      }
    ),
    (error: Error & { stdout?: string }) => {
      const summary = JSON.parse(error.stdout ?? "{}") as {
        ok: boolean;
        errors: string[];
        warnings: string[];
      };
      assert.equal(summary.ok, false);
      assert.ok(summary.errors.some((item) => item.includes("seg_map50")));
      assert.ok(summary.errors.some((item) => item.includes("box_map50")));
      assert.ok(summary.errors.some((item) => item.includes("inputSize")));
      assert.ok(summary.warnings.some((item) => item.includes("metrics split is val")));
      assert.ok(summary.warnings.some((item) => item.includes("manifest version")));
      return true;
    }
  );
});

test("verify-training-release candidate mode requires both evidence reports", async () => {
  await assert.rejects(
    execFileAsync(
      process.execPath,
      [
        "--no-warnings",
        "--experimental-strip-types",
        "scripts/verify-training-release.ts",
        "--candidate-mode",
      ],
      { cwd: path.resolve(".") }
    ),
    /requires --calibration-report and --release-test-report/
  );
});

test("verify-training-release candidate mode rejects val metrics and drifted evidence", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-training-release-candidate-fail-"));
  const datasetRoot = path.join(root, "release-test-dataset");
  const artifactsDir = path.join(root, "release-evaluation-artifacts");
  const labelsDir = path.join(artifactsDir, "labels");
  const exportsDir = path.join(root, "model", "exports", "candidate-v1");
  const modelDir = path.join(root, "public", "models", "nail-texture-seg");
  await mkdir(path.join(datasetRoot, "images", "test", "core"), { recursive: true });
  await mkdir(path.join(datasetRoot, "labels", "test", "core"), { recursive: true });
  await mkdir(labelsDir, { recursive: true });
  await mkdir(exportsDir, { recursive: true });
  await mkdir(modelDir, { recursive: true });

  const dataset = path.join(datasetRoot, "dataset.yaml");
  await writeFile(dataset, "path: .\ntrain: images/train\nval: images/val\ntest: images/test\nnames:\n  0: nail_texture\n");
  const weights = path.join(root, "best.pt");
  await writeFile(weights, "candidate-weights");
  const prediction = path.join(labelsDir, "sample.txt");
  await writeFile(prediction, "0 0.1 0.1 0.2 0.1 0.2 0.2 0.1 0.2 0.9\n");
  const fileRecords = [{ path: "labels/sample.txt", sha256: sha256(await readFile(prediction)) }];
  const filesSha256 = sha256(canonicalJson(fileRecords));
  const artifactIndex = path.join(artifactsDir, "evaluation-artifacts.json");
  await writeFile(
    artifactIndex,
    JSON.stringify({
      schema_version: 1,
      split: "val",
      artifacts_dir: artifactsDir,
      files: ["labels/sample.txt"],
      file_records: fileRecords,
      files_sha256: filesSha256,
      prediction_records: [{
        stem: "sample",
        path: "labels/sample.txt",
        sha256: fileRecords[0]!.sha256,
        prediction_count: 1,
      }],
      prediction_records_sha256: sha256(canonicalJson([{
        stem: "sample",
        path: "labels/sample.txt",
        sha256: fileRecords[0]!.sha256,
        prediction_count: 1,
      }])),
    })
  );
  const metrics = path.join(exportsDir, "metrics.json");
  await writeFile(
    metrics,
    JSON.stringify({
      dataset_yaml: dataset,
      dataset_root: datasetRoot,
      dataset_yaml_sha256: sha256(await readFile(dataset)),
      weights,
      weights_sha256: "0".repeat(64),
      output: metrics,
      artifacts_dir: artifactsDir,
      artifact_index: artifactIndex,
      split: "val",
      imgsz: 512,
      device: "auto",
      dry_run: false,
      box_map50: 0.9,
      box_map: 0.8,
      seg_map50: 0.8,
      seg_map: 0.7,
      source_dataset_inventory_sha256_before: "1".repeat(64),
      source_dataset_inventory_sha256_after: "1".repeat(64),
      source_dataset_unchanged: true,
      evaluation_artifacts: {
        directory: artifactsDir,
        index: artifactIndex,
        index_sha256: sha256(await readFile(artifactIndex)),
        files_sha256: filesSha256,
      },
    })
  );
  const releaseReport = path.join(root, "release-test-report.json");
  await writeFile(
    releaseReport,
    JSON.stringify({
      schemaVersion: 2,
      ok: true,
      status: "PASS",
      decision: "evaluation_only_frozen_reviewed_snapshot",
      trainingUse: "prohibited",
      datasetYaml: dataset,
      artifacts: { datasetYaml: { path: dataset, sha256: "2".repeat(64) } },
      counts: { images: 1, trainImages: 0, validationImages: 0, testImages: 1 },
      files_sha256: "1".repeat(64),
    })
  );
  const calibrationReport = path.join(root, "calibration.json");
  await writeFile(
    calibrationReport,
    JSON.stringify({
      decision: "calibrated_threshold_ready_for_candidate_manifest",
      calibrationEligible: true,
      manifestScoreThreshold: 0.4,
      inputs: {
        datasetYamlSha256: "3".repeat(64),
        metricsSha256: "4".repeat(64),
        artifactIndexSha256: "5".repeat(64),
        weightsSha256: sha256(await readFile(weights)),
      },
    })
  );
  const modelPath = path.join(modelDir, "candidate-v1.onnx");
  await writeFile(modelPath, Buffer.alloc(300 * 1024));
  const manifest = path.join(modelDir, "manifest.json");
  await writeFile(
    manifest,
    JSON.stringify({
      version: "candidate-v1",
      inputSize: 512,
      task: "segment",
      backendPreferences: ["webgpu", "wasm"],
      modelFile: "candidate-v1.onnx",
      modelSizeBytes: 300 * 1024,
      sha256: sha256(await readFile(modelPath)),
      labels: ["nail_texture"],
      scoreThreshold: 0.4,
      scoreThresholdEvidence: {
        path: calibrationReport,
        sha256: "6".repeat(64),
        datasetYamlSha256: "3".repeat(64),
        metricsSha256: "wrong",
        artifactIndexSha256: "5".repeat(64),
        weightsSha256: sha256(await readFile(weights)),
        decision: "calibrated_threshold_ready_for_candidate_manifest",
      },
    })
  );

  await assert.rejects(
    execFileAsync(
      process.execPath,
      [
        "--no-warnings",
        "--experimental-strip-types",
        "scripts/verify-training-release.ts",
        "--metrics",
        metrics,
        "--manifest",
        manifest,
        "--candidate-mode",
        "--calibration-report",
        calibrationReport,
        "--release-test-report",
        releaseReport,
      ],
      { cwd: path.resolve(".") }
    ),
    (error: Error & { stdout?: string }) => {
      const summary = JSON.parse(error.stdout ?? "{}") as { errors: string[]; warnings: string[] };
      assert.ok(summary.errors.some((item) => item.includes("split must be test")));
      assert.ok(summary.errors.some((item) => item.includes("weights SHA-256")));
      assert.ok(summary.errors.some((item) => item.includes("dataset YAML hash")));
      assert.ok(summary.errors.some((item) => item.includes("scoreThresholdEvidence.sha256")));
      assert.ok(summary.errors.some((item) => item.includes("scoreThresholdEvidence.metricsSha256")));
      assert.equal(summary.warnings.some((item) => item.includes("metrics split is val")), false);
      return true;
    }
  );
});
