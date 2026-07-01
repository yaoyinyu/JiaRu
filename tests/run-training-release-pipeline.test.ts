import assert from "node:assert/strict";
import { execFile } from "node:child_process";
import { mkdtemp, mkdir, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { promisify } from "node:util";
import test from "node:test";

const execFileAsync = promisify(execFile);

test("run-training-release-pipeline produces a dry-run orchestration report", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-train-pipeline-dry-"));
  const outputDir = path.join(root, "model", "exports", "nail-texture-seg-v1");
  const browserDir = path.join(root, "public", "models", "nail-texture-seg");
  await mkdir(outputDir, { recursive: true });
  await mkdir(browserDir, { recursive: true });

  const { stdout } = await execFileAsync(
    process.execPath,
    [
      "--no-warnings",
      "--experimental-strip-types",
      "scripts/run-training-release-pipeline.ts",
      "--train-output-dir",
      outputDir,
      "--browser-model-dir",
      browserDir,
      "--dry-run",
    ],
    { cwd: path.resolve(".") }
  );

  const report = JSON.parse(stdout) as {
    ok: boolean;
    mode: string;
    steps: Array<{ name: string; ok: boolean; stdout?: { skipped?: boolean } }>;
  };
  assert.equal(report.ok, true);
  assert.equal(report.mode, "dry-run");
  assert.deepEqual(report.steps.map((step) => step.name), [
    "train-yolo-seg",
    "evaluate",
    "export-onnx",
    "verify-training-release",
    "run-real-model-final-audit",
  ]);
  assert.equal(report.steps.at(-1)?.stdout?.skipped, true);
});

test("run-training-release-pipeline can verify existing release artifacts without rerunning training", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-train-pipeline-verify-"));
  const outputDir = path.join(root, "model", "exports", "nail-texture-seg-v1");
  const browserDir = path.join(root, "public", "models", "nail-texture-seg");
  await mkdir(outputDir, { recursive: true });
  await mkdir(browserDir, { recursive: true });

  await writeFile(
    path.join(outputDir, "metrics.json"),
    JSON.stringify(
      {
        dataset_yaml: "model/training/dataset.yaml",
        dataset_root: "model/datasets/nail-texture-v1",
        weights: "model/exports/nail-texture-seg-v1/nail-texture-seg-v1/weights/best.pt",
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
    path.join(browserDir, "manifest.json"),
    JSON.stringify(
      {
        version: "nail-texture-seg-v1",
        inputSize: 640,
        task: "segment",
        backendPreferences: ["webgpu", "wasm"],
        modelFile: "nail-texture-seg-v1.onnx",
        labels: ["nail_texture"],
      },
      null,
      2
    ),
    "utf8"
  );
  await writeFile(path.join(browserDir, "nail-texture-seg-v1.onnx"), Buffer.alloc(1024), "binary");

  const { stdout } = await execFileAsync(
    process.execPath,
    [
      "--no-warnings",
      "--experimental-strip-types",
      "scripts/run-training-release-pipeline.ts",
      "--train-output-dir",
      outputDir,
      "--browser-model-dir",
      browserDir,
      "--skip-train",
      "--skip-evaluate",
      "--skip-export",
    ],
    { cwd: path.resolve(".") }
  );

  const report = JSON.parse(stdout) as {
    ok: boolean;
    mode: string;
    steps: Array<{ name: string; ok: boolean }>;
    artifacts: { metrics: { seg_map50: number }; manifest: { labels: string[] } };
  };
  assert.equal(report.ok, true);
  assert.equal(report.mode, "real-run");
  assert.deepEqual(report.steps.map((step) => step.name), [
    "verify-training-release",
    "run-real-model-final-audit",
  ]);
  assert.equal(report.artifacts.metrics.seg_map50, 0.8);
  assert.deepEqual(report.artifacts.manifest.labels, ["nail_texture"]);
  assert.equal((report.steps[1] as { stdout?: { skipped?: boolean } }).stdout?.skipped, true);
});

test("run-training-release-pipeline can continue into final audit when audit inputs are provided", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-train-pipeline-final-audit-"));
  const outputDir = path.join(root, "model", "exports", "nail-texture-seg-v1");
  const browserDir = path.join(root, "public", "models", "nail-texture-seg");
  await mkdir(outputDir, { recursive: true });
  await mkdir(browserDir, { recursive: true });

  await writeFile(
    path.join(outputDir, "metrics.json"),
    JSON.stringify(
      {
        dataset_yaml: "model/training/dataset.yaml",
        dataset_root: "model/datasets/nail-texture-v1",
        weights: "model/exports/nail-texture-seg-v1/nail-texture-seg-v1/weights/best.pt",
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
    path.join(browserDir, "manifest.json"),
    JSON.stringify(
      {
        version: "nail-texture-seg-v1",
        inputSize: 640,
        task: "segment",
        backendPreferences: ["webgpu", "wasm"],
        modelFile: "nail-texture-seg-v1.onnx",
        labels: ["nail_texture"],
      },
      null,
      2
    ),
    "utf8"
  );
  await writeFile(path.join(browserDir, "nail-texture-seg-v1.onnx"), Buffer.alloc(1024), "binary");

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

  const auditOutputDir = path.join(root, "audit-output");
  const imagePath = path.resolve("model/5188.jpg_wh860.jpg");
  const { stdout } = await execFileAsync(
    process.execPath,
    [
      "--no-warnings",
      "--experimental-strip-types",
      "scripts/run-training-release-pipeline.ts",
      "--train-output-dir",
      outputDir,
      "--browser-model-dir",
      browserDir,
      "--skip-train",
      "--skip-evaluate",
      "--skip-export",
      "--final-audit-image",
      imagePath,
      "--final-audit-output-dir",
      auditOutputDir,
      "--final-audit-ui-review",
      uiReviewPath,
    ],
    { cwd: path.resolve(".") }
  );

  const report = JSON.parse(stdout) as {
    ok: boolean;
    steps: Array<{ name: string; ok: boolean }>;
    artifacts: { finalAudit: { decision: { status: string } } };
  };
  assert.equal(report.ok, true);
  assert.deepEqual(report.steps.map((step) => step.name), [
    "verify-training-release",
    "run-real-model-final-audit",
  ]);
  assert.equal(report.steps[1]?.ok, true);
  assert.equal(report.artifacts.finalAudit.decision.status, "pass");
});

test("run-training-release-pipeline passes annotation debug failures through final audit summary", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-train-pipeline-failure-summary-"));
  const outputDir = path.join(root, "model", "exports", "nail-texture-seg-v1");
  const browserDir = path.join(root, "public", "models", "nail-texture-seg");
  const annotationDir = path.join(root, "annotations");
  await mkdir(outputDir, { recursive: true });
  await mkdir(browserDir, { recursive: true });
  await mkdir(annotationDir, { recursive: true });

  await writeFile(
    path.join(outputDir, "metrics.json"),
    JSON.stringify(
      {
        dataset_yaml: "model/training/dataset.yaml",
        dataset_root: "model/datasets/nail-texture-v1",
        weights: "model/exports/nail-texture-seg-v1/nail-texture-seg-v1/weights/best.pt",
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
    path.join(browserDir, "manifest.json"),
    JSON.stringify(
      {
        version: "nail-texture-seg-v1",
        inputSize: 640,
        task: "segment",
        backendPreferences: ["webgpu", "wasm"],
        modelFile: "nail-texture-seg-v1.onnx",
        labels: ["nail_texture"],
      },
      null,
      2
    ),
    "utf8"
  );
  await writeFile(path.join(browserDir, "nail-texture-seg-v1.onnx"), Buffer.alloc(1024), "binary");

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

  await writeFile(
    path.join(annotationDir, "sample-001.json"),
    JSON.stringify(
      {
        image: { fileName: "sample-001.jpg" },
        annotations: [
          {
            attributes: {
              debug: {
                warnings: ["highlight_hotspots"],
                extractionQualityWarnings: ["mask_crop_touches_edge"],
                highlightPixels: 9,
                repairedPixels: 5,
                highlightRatio: 0.15,
              },
            },
          },
        ],
      },
      null,
      2
    ),
    "utf8"
  );

  const auditOutputDir = path.join(root, "audit-output");
  const imagePath = path.resolve("model/5188.jpg_wh860.jpg");
  const { stdout } = await execFileAsync(
    process.execPath,
    [
      "--no-warnings",
      "--experimental-strip-types",
      "scripts/run-training-release-pipeline.ts",
      "--train-output-dir",
      outputDir,
      "--browser-model-dir",
      browserDir,
      "--skip-train",
      "--skip-evaluate",
      "--skip-export",
      "--final-audit-image",
      imagePath,
      "--final-audit-output-dir",
      auditOutputDir,
      "--final-audit-annotation-dir",
      annotationDir,
      "--final-audit-ui-review",
      uiReviewPath,
    ],
    { cwd: path.resolve(".") }
  );

  const report = JSON.parse(stdout) as {
    ok: boolean;
    options: { finalAuditAnnotationDir: string | null };
    artifacts: {
      finalAudit: { annotationDirPath: string | null };
      finalAuditFailureSummary: {
        totals: { derivedAnnotationFailures: number };
        categoryCounts: Record<string, number>;
      };
    };
  };
  assert.equal(report.ok, true);
  assert.equal(report.options.finalAuditAnnotationDir, annotationDir);
  assert.equal(report.artifacts.finalAudit.annotationDirPath, annotationDir);
  assert.equal(report.artifacts.finalAuditFailureSummary.totals.derivedAnnotationFailures, 3);
  assert.equal(report.artifacts.finalAuditFailureSummary.categoryCounts.postprocess, 3);
});
