import assert from "node:assert/strict";
import { mkdtemp, mkdir, readFile, writeFile } from "node:fs/promises";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { validateRealModelFirstRunRecord } from "../src/lib/nail-texture-recognition/first-run-record.ts";

const execFileAsync = promisify(execFile);

test("build-real-model-first-run-record assembles readiness browser and ui review into a valid record", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-first-run-record-"));
  const modelDir = path.join(root, "public", "models", "nail-texture-seg");
  const exportsDir = path.join(root, "model", "exports", "nail-texture-seg-v1");
  const debugDir = path.join(root, "debug");
  await mkdir(modelDir, { recursive: true });
  await mkdir(exportsDir, { recursive: true });
  await mkdir(debugDir, { recursive: true });

  const manifestPath = path.join(modelDir, "manifest.json");
  const modelPath = path.join(modelDir, "nail-texture-seg-v1.onnx");
  await writeFile(
    manifestPath,
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
  await writeFile(modelPath, Buffer.alloc(300 * 1024), "binary");

  const metricsPath = path.join(exportsDir, "metrics.json");
  await writeFile(
    metricsPath,
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
        box_map: 0.8,
        seg_map50: 0.8,
        seg_map: 0.7,
      },
      null,
      2
    ),
    "utf8"
  );

  const uiReviewPath = path.join(root, "ui-review.json");
  await writeFile(
    uiReviewPath,
    JSON.stringify(
      {
        version: "nail-real-model-ui-review/v1",
        createdAt: "2026-07-01T00:00:00.000Z",
        pagePath: "/ar-tryon",
        checks: {
          pickerOpened: true,
          modelOrFallbackBadgeVisible: true,
          pageResponsive: true,
          fallbackRecovered: true,
        },
        notes: "manual review ok",
        decision: {
          status: "pass",
          summary: "ui checks passed",
        },
      },
      null,
      2
    ),
    "utf8"
  );

  const imagePath = path.resolve("model/5188.jpg_wh860.jpg");
  const outputPath = path.join(root, "first-run-record.json");

  const { stdout } = await execFileAsync(
    process.execPath,
    [
      "--no-warnings",
      "--experimental-strip-types",
      "scripts/build-real-model-first-run-record.ts",
      "--manifest",
      manifestPath,
      "--image",
      imagePath,
      "--output",
      outputPath,
      "--debug-output-dir",
      debugDir,
      "--debug-prefix",
      "real-model",
      "--metrics",
      metricsPath,
      "--ui-review",
      uiReviewPath,
    ],
    {
      cwd: path.resolve("."),
    }
  );

  const summary = JSON.parse(stdout) as {
    ok: boolean;
    outputPath: string;
  };
  assert.equal(summary.ok, true);

  const record = JSON.parse(await readFile(outputPath, "utf8"));
  const validation = validateRealModelFirstRunRecord(record);
  assert.equal(validation.ok, true);
  assert.equal(record.model.artifactOk, true);
  assert.equal(record.input.imagePath, imagePath);
  assert.equal(record.decision.status, "pass");
});
