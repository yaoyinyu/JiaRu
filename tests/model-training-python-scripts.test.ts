import assert from "node:assert/strict";
import { execFile } from "node:child_process";
import { createHash } from "node:crypto";
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

test("candidate35 boundary evidence builders are valid Python", async () => {
  for (const script of [
    "model/training/build-sam-crop-review-sheets.py",
    "model/training/build-candidate35-combined-training-truth-index.py",
  ]) {
    await execFileAsync("python", [
      "-c",
      "from pathlib import Path; import sys; p=Path(sys.argv[1]); compile(p.read_text(encoding='utf-8'), str(p), 'exec')",
      script,
    ], {
      cwd: path.resolve("."),
    });
  }
});

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
  assert.equal(result.mosaic, 1);
  assert.equal(result.close_mosaic, 10);
  assert.equal(result.mask_ratio, 4);
  assert.equal(result.overlap_mask, true);
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

test("train script freezes full-resolution boundary-preserving settings", async () => {
  const result = await runPython("model/training/train-yolo-seg.py", [
    "--dry-run",
    "--mosaic", "0",
    "--close-mosaic", "0",
    "--mask-ratio", "1",
    "--no-overlap-mask",
  ]);
  assert.equal(result.mosaic, 0);
  assert.equal(result.close_mosaic, 0);
  assert.equal(result.mask_ratio, 1);
  assert.equal(result.overlap_mask, false);
});

test("train script hash-binds an interrupted checkpoint for exact resume", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-training-resume-"));
  const outputDir = path.join(root, "output");
  const runDir = path.join(outputDir, "resume-run");
  const checkpoint = path.join(runDir, "weights", "last.pt");
  await mkdir(path.dirname(checkpoint), { recursive: true });
  await writeFile(checkpoint, "checkpoint-state", "utf8");
  const runtimeDataset = path.join(outputDir, "resolved-dataset.yaml");
  await writeFile(path.join(runDir, "args.yaml"), [
    `model: ${path.resolve("yolo11n-seg.pt")}`,
    `data: ${runtimeDataset}`,
    "epochs: 100",
    "patience: 20",
    "batch: -1",
    "imgsz: 640",
    "device: auto",
    "workers: 8",
    `project: ${outputDir}`,
    "name: resume-run",
    "optimizer: auto",
    "close_mosaic: 10",
    "freeze: null",
    "overlap_mask: true",
    "mask_ratio: 4",
    "mosaic: 1.0",
    "lr0: null",
  ].join("\n"), "utf8");
  await writeFile(path.join(runDir, "results.csv"), "epoch,time\n1,1.0\n", "utf8");
  const result = await runPython("model/training/train-yolo-seg.py", [
    "--dry-run",
    "--output-dir", outputDir,
    "--run-name", "resume-run",
    "--resume-from", checkpoint,
  ]);
  const resume = result.resume_from as { path: string; sha256: string; bytes: number; completed_epochs: number; quality_parameters_unchanged: boolean };
  assert.equal(resume.path, path.resolve(checkpoint));
  assert.equal(resume.bytes, Buffer.byteLength("checkpoint-state"));
  assert.match(resume.sha256, /^[a-f0-9]{64}$/);
  assert.equal(resume.completed_epochs, 1);
  assert.equal(resume.quality_parameters_unchanged, true);
});

test("checkpoint interpolation creates a hash-bound student artifact", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-checkpoint-interpolation-"));
  const base = path.join(root, "base.pt");
  const candidate = path.join(root, "candidate.pt");
  const output = path.join(root, "interpolated.pt");
  const report = path.join(root, "report.json");
  const makeCheckpoints = [
    "import sys, torch",
    "from torch import nn",
    "base = nn.Sequential(nn.Linear(2, 2, bias=False))",
    "candidate = nn.Sequential(nn.Linear(2, 2, bias=False))",
    "base[0].weight.data.fill_(0.0)",
    "candidate[0].weight.data.fill_(2.0)",
    "torch.save({'model': base}, sys.argv[1])",
    "torch.save({'model': candidate}, sys.argv[2])",
  ].join("; ");
  await execFileAsync("python", ["-c", makeCheckpoints, base, candidate]);
  const result = await runPython("model/training/interpolate-yolo-checkpoints.py", [
    "--base", base,
    "--candidate", candidate,
    "--alpha", "0.25",
    "--output", output,
    "--report", report,
  ]);
  assert.equal(result.ok, true);
  assert.equal(result.alpha, 0.25);
  assert.equal((result.structure as { stateTensorCount: number }).stateTensorCount, 1);
  assert.equal((result.output as { sha256: string }).sha256.length, 64);
  const verify = [
    "import sys, torch",
    "checkpoint = torch.load(sys.argv[1], map_location='cpu', weights_only=False)",
    "print(float(checkpoint['model'][0].weight.mean()))",
  ].join("; ");
  const { stdout } = await execFileAsync("python", ["-c", verify, output]);
  assert.equal(Number(stdout.trim()), 0.5);
});

test("train script freezes a local multi-signal distillation contract", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-distillation-plan-"));
  const student = path.join(root, "student.pt");
  const teacher = path.join(root, "teacher.pt");
  await writeFile(student, "student-checkpoint", "utf8");
  await writeFile(teacher, "teacher-checkpoint", "utf8");
  const result = await runPython("model/training/train-yolo-seg.py", [
    "--dry-run",
    "--model", student,
    "--distill-model", teacher,
    "--distill-weight", "1.25",
    "--distill-temperature", "2.5",
    "--distill-topk", "16",
  ]);
  const distillation = result.distillation as {
    teacher: { sha256: string };
    studentBase: { sha256: string };
    contract: { temperature: number; feature_weight: number; topk_anchors: number; signals: string[] };
  };
  assert.notEqual(distillation.teacher.sha256, distillation.studentBase.sha256);
  assert.equal(distillation.contract.temperature, 2.5);
  assert.equal(distillation.contract.feature_weight, 1.25);
  assert.equal(distillation.contract.topk_anchors, 16);
  assert.deepEqual(distillation.contract.signals, [
    "teacher-score-weighted-neck-features",
    "bernoulli-soft-class-probabilities",
    "distribution-focal-box-logits",
    "anchor-aligned-soft-instance-masks",
    "soft-mask-boundary-gradients",
  ]);
});

test("train script requires an explicit switch for same-checkpoint self-distillation", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-self-distillation-plan-"));
  const checkpoint = path.join(root, "same.pt");
  await writeFile(checkpoint, "same-checkpoint", "utf8");
  await assert.rejects(
    runPython("model/training/train-yolo-seg.py", [
      "--dry-run",
      "--model", checkpoint,
      "--distill-model", checkpoint,
    ]),
    /allow-same-checkpoint-self-distillation/,
  );
  const result = await runPython("model/training/train-yolo-seg.py", [
    "--dry-run",
    "--model", checkpoint,
    "--distill-model", checkpoint,
    "--allow-same-checkpoint-self-distillation",
  ]);
  const distillation = result.distillation as {
    mode: string;
    sameCheckpointExplicitlyAuthorized: boolean;
  };
  assert.equal(distillation.mode, "same-checkpoint-self-distillation");
  assert.equal(distillation.sameCheckpointExplicitlyAuthorized, true);
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
  assert.equal(result.plots, true);
  assert.equal(result.dry_run, true);
});

test("evaluate script can disable optional plots without disabling prediction artifacts", async () => {
  const result = await runPython("model/training/evaluate.py", ["--no-plots", "--dry-run"]);
  assert.equal(result.plots, false);
  assert.equal(result.dry_run, true);
});

test("evaluate script persists visual evaluation artifact index and metrics", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-evaluate-artifacts-"));
  const fakeModuleDir = path.join(root, "fake-python-modules");
  const outputDir = path.join(root, "output");
  const artifactsDir = path.join(outputDir, "evaluation-artifacts");
  const metricsPath = path.join(outputDir, "metrics.json");
  const weightsPath = path.join(root, "best.pt");
  const datasetRoot = path.join(root, "source-dataset");
  const datasetPath = path.join(datasetRoot, "dataset.yaml");
  for (const folder of ["images/train", "images/val", "images/test", "labels/train", "labels/val", "labels/test"]) {
    await mkdir(path.join(datasetRoot, folder), { recursive: true });
  }
  await writeFile(path.join(datasetRoot, "images", "test", "sample-001.jpg"), "fixture-image", "utf8");
  await writeFile(path.join(datasetRoot, "labels", "test", "sample-001.txt"), "0 0.1 0.1 0.2 0.1 0.2 0.2 0.1 0.2\n", "utf8");
  await writeFile(datasetPath, [
    "path: .", "train: images/train", "val: images/val", "test: images/test", "",
    "names:", "  0: nail_texture", "", "task: segment", "class_count: 1", "image_size: 640", "",
  ].join("\n"), "utf8");
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
      "        runtime_root = Path(kwargs['data']).parent",
      "        (runtime_root / 'labels' / 'test' / 'test.cache').write_text('runtime-only-cache', encoding='utf-8')",
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
      "--dataset",
      datasetPath,
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
      index_sha256: string;
      files_sha256: string;
      counts: { total: number; plots: number; prediction_labels: number };
    };
    dataset_yaml_sha256: string;
    weights_sha256: string;
    source_dataset_inventory_sha256_before: string;
    source_dataset_inventory_sha256_after: string;
    source_dataset_unchanged: boolean;
    runtime_dataset_root: string;
    runtime_dataset_inventory_sha256: string;
    runtime_materialization_records: Array<{
      sourceImage: string;
      sourceLabel: string;
      runtimeImage: string;
      runtimeLabel: string;
      imageMaterialization: string;
      labelMaterialization: string;
    }>;
  };
  const artifactIndex = JSON.parse(
    await readFile(path.join(artifactsDir, "evaluation-artifacts.json"), "utf8")
  ) as {
    split: string;
    files: string[];
    file_records: Array<{ path: string; sha256: string }>;
    files_sha256: string;
    prediction_records: Array<{ stem: string; path: string | null; sha256: string | null; prediction_count: number }>;
    prediction_records_sha256: string;
  };
  const sha256 = (value: Buffer | string) => createHash("sha256").update(value).digest("hex");
  assert.equal(metrics.seg_map50, 0.8);
  assert.equal(metrics.evaluation_artifacts.counts.total, 5);
  assert.equal(metrics.evaluation_artifacts.counts.plots, 3);
  assert.equal(metrics.evaluation_artifacts.counts.prediction_labels, 1);
  assert.equal(artifactIndex.split, "test");
  assert.deepEqual(artifactIndex.files, [...artifactIndex.files].sort());
  assert.deepEqual(
    artifactIndex.file_records.map((item) => item.path),
    artifactIndex.files
  );
  assert.ok(artifactIndex.files.includes("confusion_matrix.png"));
  assert.ok(artifactIndex.files.includes("val_batch0_pred.jpg"));
  assert.equal(metrics.dataset_yaml_sha256, sha256(await readFile(datasetPath)));
  assert.equal(metrics.weights_sha256, sha256(await readFile(weightsPath)));
  assert.equal(metrics.source_dataset_unchanged, true);
  assert.equal(
    metrics.source_dataset_inventory_sha256_before,
    metrics.source_dataset_inventory_sha256_after
  );
  assert.equal(metrics.runtime_materialization_records.length, 1);
  assert.equal(metrics.runtime_materialization_records[0]?.imageMaterialization, "copy");
  assert.equal(metrics.runtime_materialization_records[0]?.labelMaterialization, "copy");
  assert.match(metrics.runtime_dataset_inventory_sha256, /^[a-f0-9]{64}$/);
  assert.equal(
    await readFile(path.join(metrics.runtime_dataset_root, "labels", "test", "test.cache"), "utf8"),
    "runtime-only-cache"
  );
  await assert.rejects(readFile(path.join(datasetRoot, "labels", "test.cache"), "utf8"));
  await assert.rejects(readFile(path.join(datasetRoot, "labels", "test", "test.cache"), "utf8"));
  assert.equal(
    metrics.evaluation_artifacts.index_sha256,
    sha256(await readFile(path.join(artifactsDir, "evaluation-artifacts.json")))
  );
  assert.equal(metrics.evaluation_artifacts.files_sha256, artifactIndex.files_sha256);
  assert.equal(artifactIndex.file_records.length, artifactIndex.files.length);
  assert.deepEqual(artifactIndex.prediction_records, [{
    stem: "sample-001",
    path: "labels/sample-001.txt",
    sha256: sha256(await readFile(path.join(artifactsDir, "labels", "sample-001.txt"))),
    prediction_count: 1,
  }]);
  assert.match(artifactIndex.prediction_records_sha256, /^[a-f0-9]{64}$/);
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

test("candidate ONNX export requires a calibration report and forbids a manual threshold", async () => {
  const missingReport = await execFileAsync(
    "python",
    ["model/training/export-onnx.py", "--candidate-mode", "--dry-run"],
    { cwd: path.resolve(".") }
  ).then(
    () => null,
    (error: { stderr?: string }) => error
  );
  assert.ok(missingReport);
  assert.match(missingReport.stderr ?? "", /requires --calibration-report/);

  const manualThreshold = await execFileAsync(
    "python",
    [
      "model/training/export-onnx.py",
      "--candidate-mode",
      "--calibration-report", "unused.json",
      "--score-threshold", "0.42",
      "--dry-run",
    ],
    { cwd: path.resolve(".") }
  ).then(
    () => null,
    (error: { stderr?: string }) => error
  );
  assert.ok(manualThreshold);
  assert.match(manualThreshold.stderr ?? "", /--score-threshold is prohibited/);
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
