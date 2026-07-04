import assert from "node:assert/strict";
import { execFile } from "node:child_process";
import { mkdtemp, mkdir, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { promisify } from "node:util";
import test from "node:test";

const execFileAsync = promisify(execFile);

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
