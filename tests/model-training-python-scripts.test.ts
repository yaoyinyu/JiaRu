import assert from "node:assert/strict";
import { execFile } from "node:child_process";
import { mkdtemp, mkdir, readFile, writeFile } from "node:fs/promises";
import { promisify } from "node:util";
import os from "node:os";
import path from "node:path";
import test from "node:test";

const execFileAsync = promisify(execFile);

async function runPython(script: string, args: string[] = []) {
  const { stdout } = await execFileAsync(
    "python",
    [script, ...args],
    {
      cwd: path.resolve("."),
    }
  );
  return JSON.parse(stdout) as Record<string, unknown>;
}

test("dataset yaml exists and contains expected paths", async () => {
  const fs = await import("node:fs/promises");
  const yaml = await fs.readFile("model/training/dataset.yaml", "utf8");
  assert.match(yaml, /^path: \.\.\/datasets\/nail-texture-v1/m);
  assert.match(yaml, /^train: images\/train/m);
  assert.match(yaml, /^val: images\/val/m);
  assert.match(yaml, /^test: images\/test/m);
});

test("train script dry-run resolves dataset and hyperparameters", async () => {
  const result = await runPython("model/training/train-yolo-seg.py", ["--dry-run"]);
  assert.equal(result.task, "segment");
  assert.equal(result.class_count, 1);
  assert.equal(result.imgsz, 640);
  assert.equal(result.batch, -1);
  assert.match(String(result.runtime_dataset_yaml), /resolved-dataset\.yaml$/);
  assert.match(String(result.best_weights_path), /model[\\/]+exports[\\/]+nail-texture-seg-v1[\\/]+nail-texture-seg-v1[\\/]+weights[\\/]+best\.pt$/);
  assert.equal(result.training_intent, "experiment");
  assert.equal(result.candidate_validation_evidence, null);
  assert.equal(result.dry_run, true);
});

test("train script normalizes automatic and fractional batch settings", async () => {
  const automatic = await runPython("model/training/train-yolo-seg.py", ["--dry-run", "--batch", "auto"]);
  const fractional = await runPython("model/training/train-yolo-seg.py", ["--dry-run", "--batch", "0.7"]);
  assert.equal(automatic.batch, -1);
  assert.equal(fractional.batch, 0.7);
});


test("training environment preflight reports dataset, dependencies, and checkpoint risk", async () => {
  const result = await runPython("model/training/check-training-environment.py");
  const split = JSON.parse(
    await readFile("model/datasets/nail-texture-v1/metadata/split.json", "utf8")
  ) as Record<"train" | "val" | "test", string[]>;
  assert.deepEqual(result.split_counts, {
    train: split.train.length,
    val: split.val.length,
    test: split.test.length,
  });
  assert.equal(typeof (result.dependencies as { ultralytics: { available: boolean } }).ultralytics.available, "boolean");
  const model = result.model as { exists: boolean; may_download: boolean };
  assert.equal(model.may_download, !model.exists);
  if (model.may_download) {
    assert.ok(
      (result.warnings as string[]).some((warning) => warning.includes("may download it"))
    );
  }
});

test("training environment preflight can require a local model checkpoint", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-training-env-"));
  const weightsPath = path.join(root, "local-yolo-seg.pt");
  await writeFile(weightsPath, "fake weights", "utf8");

  const result = await runPython("model/training/check-training-environment.py", [
    "--model",
    weightsPath,
    "--require-local-model",
  ]);
  assert.equal((result.model as { exists: boolean }).exists, true);
  assert.equal((result.model as { may_download: boolean }).may_download, false);
  assert.ok(
    (result.checks as Array<{ name: string; ok: boolean }>).some(
      (check) => check.name === "local_model_available" && check.ok
    )
  );
});
test("evaluate script dry-run prints resolved config", async () => {
  const result = await runPython("model/training/evaluate.py", ["--dry-run"]);
  assert.equal(result.split, "test");
  assert.equal(result.imgsz, 640);
  assert.match(String(result.weights), /model[\\/]+exports[\\/]+nail-texture-seg-v1[\\/]+nail-texture-seg-v1[\\/]+weights[\\/]+best\.pt$/);
  assert.match(
    String(result.artifact_index),
    /model[\\/]+exports[\\/]+nail-texture-seg-v1[\\/]+evaluation-artifacts[\\/]+evaluation-artifacts\.json$/
  );
  assert.equal(result.dry_run, true);
});

test("evaluate script persists visual evaluation artifact index and metrics", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-evaluate-artifacts-"));
  const fakeModuleDir = path.join(root, "fake-python-modules");
  const outputDir = path.join(root, "output");
  const artifactsDir = path.join(outputDir, "evaluation-artifacts");
  const metricsPath = path.join(outputDir, "metrics.json");
  const weightsPath = path.join(root, "best.pt");
  await mkdir(fakeModuleDir, { recursive: true });
  await writeFile(weightsPath, "fake", "utf8");
  await writeFile(
    path.join(fakeModuleDir, "ultralytics.py"),
    [
      "from pathlib import Path",
      "class _Metric:",
      "    map50 = 0.8",
      "    map = 0.7",
      "class _Metrics:",
      "    box = _Metric()",
      "    seg = _Metric()",
      "    def __init__(self, save_dir):",
      "        self.save_dir = save_dir",
      "class YOLO:",
      "    def __init__(self, weights):",
      "        self.weights = weights",
      "    def val(self, **kwargs):",
      "        save_dir = Path(kwargs['project']) / kwargs['name']",
      "        (save_dir / 'labels').mkdir(parents=True, exist_ok=True)",
      "        for name in ['confusion_matrix.png', 'PR_curve.png', 'val_batch0_pred.jpg', 'predictions.json']:",
      "            (save_dir / name).write_text('fixture', encoding='utf-8')",
      "        (save_dir / 'labels' / 'sample-001.txt').write_text('0 0.9', encoding='utf-8')",
      "        return _Metrics(save_dir)",
    ].join("\n"),
    "utf8"
  );

  await execFileAsync(
    "python",
    [
      "model/training/evaluate.py",
      "--weights",
      weightsPath,
      "--output",
      metricsPath,
      "--artifacts-dir",
      artifactsDir,
    ],
    {
      cwd: path.resolve("."),
      env: { ...process.env, PYTHONPATH: fakeModuleDir },
    }
  );

  const metrics = JSON.parse(await readFile(metricsPath, "utf8")) as {
    seg_map50: number;
    evaluation_artifacts: {
      index: string;
      counts: { total: number; plots: number; prediction_labels: number };
    };
  };
  const artifactIndex = JSON.parse(
    await readFile(path.join(artifactsDir, "evaluation-artifacts.json"), "utf8")
  ) as { split: string; files: string[] };
  assert.equal(metrics.seg_map50, 0.8);
  assert.equal(metrics.evaluation_artifacts.counts.total, 5);
  assert.equal(metrics.evaluation_artifacts.counts.plots, 3);
  assert.equal(metrics.evaluation_artifacts.counts.prediction_labels, 1);
  assert.equal(artifactIndex.split, "test");
  assert.ok(artifactIndex.files.includes("confusion_matrix.png"));
  assert.ok(artifactIndex.files.includes("val_batch0_pred.jpg"));
});
test("export onnx script dry-run prints manifest target", async () => {
  const result = await runPython("model/training/export-onnx.py", ["--dry-run"]);
  assert.equal(result.model_version, "nail-texture-seg-v1");
  assert.equal(result.input_size, 640);
  assert.deepEqual(result.backend_preferences, ["webgpu", "wasm"]);
  assert.deepEqual(result.labels, ["nail_texture"]);
  assert.equal(result.score_threshold, 0.35);
  assert.equal(result.dry_run, true);
  assert.match(String(result.manifest_path), /public[\\/]+models[\\/]+nail-texture-seg[\\/]+manifest\.json$/);
});

test("export onnx script writes manifest integrity metadata", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-export-onnx-integrity-"));
  const fakeModuleDir = path.join(root, "fake-python-modules");
  const weightsPath = path.join(root, "best.pt");
  const exportedPath = path.join(root, "exported.onnx");
  const outputDir = path.join(root, "public", "models", "nail-texture-seg");
  await mkdir(fakeModuleDir, { recursive: true });
  await writeFile(weightsPath, "fake weights", "utf8");
  await writeFile(exportedPath, Buffer.alloc(300 * 1024), "binary");
  await writeFile(
    path.join(fakeModuleDir, "ultralytics.py"),
    [
      "class YOLO:",
      "    def __init__(self, weights):",
      "        self.weights = weights",
      "    def export(self, **kwargs):",
      `        return r'${exportedPath.replaceAll("\\", "\\\\")}'`,
    ].join("\n"),
    "utf8"
  );

  await execFileAsync(
    "python",
    [
      "model/training/export-onnx.py",
      "--weights",
      weightsPath,
      "--output-dir",
      outputDir,
      "--model-version",
      "nail-texture-seg-v1",
    ],
    {
      cwd: path.resolve("."),
      env: { ...process.env, PYTHONPATH: fakeModuleDir },
    }
  );

  const manifest = JSON.parse(await readFile(path.join(outputDir, "manifest.json"), "utf8")) as {
    modelSizeBytes: number;
    sha256: string;
    modelFile: string;
    scoreThreshold: number;
  };
  assert.equal(manifest.modelFile, "nail-texture-seg-v1.onnx");
  assert.equal(manifest.modelSizeBytes, 300 * 1024);
  assert.equal(manifest.sha256, "7818f5542a0404157573be6cffc0e0c8e68ce3c0f5d17d07ccdd9313fb700baf");
  assert.equal(manifest.scoreThreshold, 0.35);
});
