import assert from "node:assert/strict";
import { execFile } from "node:child_process";
import { mkdtemp, mkdir, readFile, writeFile } from "node:fs/promises";
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

test("run-training-release-pipeline aligns default runName and trainOutputDir with modelVersion", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-train-pipeline-model-version-defaults-"));
  const browserDir = path.join(root, "public", "models", "nail-texture-seg");
  await mkdir(browserDir, { recursive: true });

  const { stdout } = await execFileAsync(
    process.execPath,
    [
      "--no-warnings",
      "--experimental-strip-types",
      "scripts/run-training-release-pipeline.ts",
      "--browser-model-dir",
      browserDir,
      "--model-version",
      "nail-texture-seg-v9",
      "--dry-run",
    ],
    { cwd: path.resolve(".") }
  );

  const report = JSON.parse(stdout) as {
    ok: boolean;
    paths: { trainOutputDir: string };
    options: { runName: string; modelVersion: string };
  };
  assert.equal(report.ok, true);
  assert.equal(report.options.modelVersion, "nail-texture-seg-v9");
  assert.equal(report.options.runName, "nail-texture-seg-v9");
  assert.match(report.paths.trainOutputDir, /model[\\/]+exports[\\/]+nail-texture-seg-v9$/);
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

test("run-training-release-pipeline can continue into release governance when enabled", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-train-pipeline-governance-"));
  const outputDir = path.join(root, "model", "exports", "nail-texture-seg-v2");
  const browserDir = path.join(root, "public", "models", "nail-texture-seg");
  await mkdir(outputDir, { recursive: true });
  await mkdir(browserDir, { recursive: true });

  await writeFile(
    path.join(outputDir, "metrics.json"),
    JSON.stringify(
      {
        dataset_yaml: "model/training/dataset.yaml",
        dataset_root: "model/datasets/nail-texture-v1",
        weights: "model/exports/nail-texture-seg-v2/nail-texture-seg-v2/weights/best.pt",
        output: "model/exports/nail-texture-seg-v2/metrics.json",
        split: "test",
        imgsz: 640,
        device: "auto",
        dry_run: false,
        box_map50: 0.91,
        box_map: 0.83,
        seg_map50: 0.81,
        seg_map: 0.72,
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
        version: "nail-texture-seg-v2",
        inputSize: 640,
        task: "segment",
        backendPreferences: ["webgpu", "wasm"],
        modelFile: "nail-texture-seg-v2.onnx",
        labels: ["nail_texture"],
      },
      null,
      2
    ),
    "utf8"
  );
  await writeFile(path.join(browserDir, "nail-texture-seg-v2.onnx"), Buffer.alloc(1024), "binary");

  const uiReviewPath = path.join(root, "ui-review.json");
  await writeFile(
    uiReviewPath,
    JSON.stringify(
      {
        version: "nail-real-model-ui-review/v1",
        createdAt: "2026-07-02T00:00:00.000Z",
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

  const compareSummaryPath = path.join(outputDir, "compare-summary.json");
  await writeFile(
    compareSummaryPath,
    JSON.stringify(
      {
        ok: true,
        regressions: [],
        improvements: ["seg_map50 improved by 0.02"],
        warnings: [],
      },
      null,
      2
    ),
    "utf8"
  );

  const releaseTraceDraftPath = path.join(outputDir, "release-trace-draft.json");
  await writeFile(
    releaseTraceDraftPath,
    JSON.stringify(
      {
        draft: true,
        batch: {
          rootDir: "C:/tmp/seed-batch-020",
          sourceGroup: "seed-batch-020",
          datasetRoot: "C:/tmp/dataset",
          reviewedImportReportPath: "C:/tmp/dataset/metadata/reviewed-import-seed-batch-020.report.json",
          importedFileCount: 6,
        },
      },
      null,
      2
    ),
    "utf8"
  );

  const registryPath = path.join(browserDir, "release-registry.json");
  await writeFile(
    registryPath,
    JSON.stringify(
      {
        currentVersion: "nail-texture-seg-v1",
        releases: [{ version: "nail-texture-seg-v1" }],
      },
      null,
      2
    ),
    "utf8"
  );

  const historyManifestPath = path.join(outputDir, "release-history-manifest.json");
  const auditOutputDir = path.join(outputDir, "real-model-final-audit");
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
      "--run-governance",
      "--governance-compare-summary",
      compareSummaryPath,
      "--governance-registry",
      registryPath,
      "--governance-release-trace-draft",
      releaseTraceDraftPath,
      "--governance-history-manifest",
      historyManifestPath,
    ],
    { cwd: path.resolve(".") }
  );

  const report = JSON.parse(stdout) as {
    ok: boolean;
    steps: Array<{ name: string; ok: boolean }>;
    options: { runGovernance: boolean; governanceCompareSummary: string | null };
    paths: { governanceReportPath: string | null };
    artifacts: {
      releaseGovernance: {
        ok: boolean;
        artifacts: {
          releaseDecision: { decision: { status: string } };
          promotion: { registerSummary: { registeredVersion: string } };
          historyManifest: { totals: { traceIndexes: number } };
        };
      } | null;
    };
  };
  assert.equal(report.ok, true);
  assert.equal(report.options.runGovernance, true);
  assert.equal(report.options.governanceCompareSummary, compareSummaryPath);
  assert.equal(report.steps.at(-1)?.name, "run-release-governance-pipeline");
  assert.equal(report.steps.at(-1)?.ok, true);
  assert.ok(report.paths.governanceReportPath);
  assert.equal(report.artifacts.releaseGovernance?.ok, true);
  assert.equal(
    report.artifacts.releaseGovernance?.artifacts.releaseDecision.decision.status,
    "approve_candidate"
  );
  assert.equal(
    report.artifacts.releaseGovernance?.artifacts.promotion.registerSummary.registeredVersion,
    "nail-texture-seg-v2"
  );
  assert.equal(
    report.artifacts.releaseGovernance?.artifacts.historyManifest.totals.traceIndexes,
    1
  );

  const savedHistory = JSON.parse(await readFile(historyManifestPath, "utf8")) as {
    entries: Array<{ candidateVersion: string | null }>;
  };
  assert.equal(savedHistory.entries[0]?.candidateVersion, "nail-texture-seg-v2");
});

test("run-training-release-pipeline can auto-resolve reviewed batch governance inputs from root dir", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-train-pipeline-governance-rootdir-"));
  const outputDir = path.join(root, "model", "exports", "nail-texture-seg-v2");
  const browserDir = path.join(root, "public", "models", "nail-texture-seg");
  const batchRootDir = path.join(root, "seed-batch-020");
  await mkdir(outputDir, { recursive: true });
  await mkdir(browserDir, { recursive: true });
  await mkdir(batchRootDir, { recursive: true });

  await writeFile(
    path.join(outputDir, "metrics.json"),
    JSON.stringify(
      {
        dataset_yaml: "model/training/dataset.yaml",
        dataset_root: "model/datasets/nail-texture-v1",
        weights: "model/exports/nail-texture-seg-v2/nail-texture-seg-v2/weights/best.pt",
        output: "model/exports/nail-texture-seg-v2/metrics.json",
        split: "test",
        imgsz: 640,
        device: "auto",
        dry_run: false,
        box_map50: 0.91,
        box_map: 0.83,
        seg_map50: 0.81,
        seg_map: 0.72,
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
        version: "nail-texture-seg-v2",
        inputSize: 640,
        task: "segment",
        backendPreferences: ["webgpu", "wasm"],
        modelFile: "nail-texture-seg-v2.onnx",
        labels: ["nail_texture"],
      },
      null,
      2
    ),
    "utf8"
  );
  await writeFile(path.join(browserDir, "nail-texture-seg-v2.onnx"), Buffer.alloc(1024), "binary");

  const uiReviewPath = path.join(root, "ui-review.json");
  await writeFile(
    uiReviewPath,
    JSON.stringify(
      {
        version: "nail-real-model-ui-review/v1",
        createdAt: "2026-07-02T00:00:00.000Z",
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

  const compareSummaryPath = path.join(outputDir, "compare-summary.json");
  await writeFile(
    compareSummaryPath,
    JSON.stringify(
      {
        ok: true,
        regressions: [],
        improvements: ["seg_map50 improved by 0.02"],
        warnings: [],
      },
      null,
      2
    ),
    "utf8"
  );

  const releaseTraceDraftPath = path.join(batchRootDir, "release-trace-draft.json");
  await writeFile(
    releaseTraceDraftPath,
    JSON.stringify(
      {
        draft: true,
        batch: {
          rootDir: batchRootDir,
          sourceGroup: "seed-batch-020",
          datasetRoot: "C:/tmp/dataset",
          reviewedImportReportPath: "C:/tmp/dataset/metadata/reviewed-import-seed-batch-020.report.json",
          importedFileCount: 6,
        },
      },
      null,
      2
    ),
    "utf8"
  );

  const reviewedBatchImportPipelineReportPath = path.join(
    batchRootDir,
    "reviewed-batch-import-pipeline-report.json"
  );
  await writeFile(
    reviewedBatchImportPipelineReportPath,
    JSON.stringify(
      {
        ok: true,
        rootDir: batchRootDir,
        reportPath: reviewedBatchImportPipelineReportPath,
        steps: [
          {
            name: "import-reviewed-batch",
            stdout: {
              sourceGroup: "seed-batch-020",
              datasetRoot: "C:/tmp/dataset",
              reportPath: "C:/tmp/dataset/metadata/reviewed-import-seed-batch-020.report.json",
              importedDocuments: Array.from({ length: 6 }, (_, index) => ({
                fileName: `sample-00${index + 1}.jpg`,
              })),
            },
          },
        ],
      },
      null,
      2
    ),
    "utf8"
  );

  const registryPath = path.join(browserDir, "release-registry.json");
  await writeFile(
    registryPath,
    JSON.stringify(
      {
        currentVersion: "nail-texture-seg-v1",
        releases: [{ version: "nail-texture-seg-v1" }],
      },
      null,
      2
    ),
    "utf8"
  );

  const historyManifestPath = path.join(outputDir, "release-history-manifest.json");
  const auditOutputDir = path.join(outputDir, "real-model-final-audit");
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
      "--run-governance",
      "--governance-compare-summary",
      compareSummaryPath,
      "--governance-registry",
      registryPath,
      "--governance-reviewed-batch-root-dir",
      batchRootDir,
      "--governance-history-manifest",
      historyManifestPath,
    ],
    { cwd: path.resolve(".") }
  );

  const report = JSON.parse(stdout) as {
    ok: boolean;
    options: {
      governanceReleaseTraceDraft: string | null;
      governanceReviewedBatchImportPipelineReport: string | null;
      governanceReviewedBatchRootDir: string | null;
    };
    artifacts: {
      releaseGovernance: {
        ok: boolean;
        artifacts: {
          traceIndex: {
            batch: {
              sourceGroup: string | null;
              releaseTraceDraftPath: string | null;
              reviewedBatchImportPipelineReportPath: string | null;
            } | null;
          };
        };
      } | null;
    };
  };

  assert.equal(report.ok, true);
  assert.equal(report.options.governanceReviewedBatchRootDir, batchRootDir);
  assert.equal(report.options.governanceReleaseTraceDraft, releaseTraceDraftPath);
  assert.equal(
    report.options.governanceReviewedBatchImportPipelineReport,
    reviewedBatchImportPipelineReportPath
  );
  assert.equal(report.artifacts.releaseGovernance?.ok, true);
  assert.equal(
    report.artifacts.releaseGovernance?.artifacts.traceIndex.batch?.sourceGroup,
    "seed-batch-020"
  );
  assert.equal(
    report.artifacts.releaseGovernance?.artifacts.traceIndex.batch?.releaseTraceDraftPath,
    releaseTraceDraftPath
  );
  assert.equal(
    report.artifacts.releaseGovernance?.artifacts.traceIndex.batch?.reviewedBatchImportPipelineReportPath,
    reviewedBatchImportPipelineReportPath
  );
});

test("run-training-release-pipeline can prioritize reviewed batch release handoff as governance input", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-train-pipeline-governance-handoff-"));
  const outputDir = path.join(root, "model", "exports", "nail-texture-seg-v2");
  const browserDir = path.join(root, "public", "models", "nail-texture-seg");
  const batchRootDir = path.join(root, "seed-batch-030");
  await mkdir(outputDir, { recursive: true });
  await mkdir(browserDir, { recursive: true });
  await mkdir(batchRootDir, { recursive: true });

  await writeFile(
    path.join(outputDir, "metrics.json"),
    JSON.stringify(
      {
        dataset_yaml: "model/training/dataset.yaml",
        dataset_root: "model/datasets/nail-texture-v1",
        weights: "model/exports/nail-texture-seg-v2/nail-texture-seg-v2/weights/best.pt",
        output: "model/exports/nail-texture-seg-v2/metrics.json",
        split: "test",
        imgsz: 640,
        device: "auto",
        dry_run: false,
        box_map50: 0.91,
        box_map: 0.83,
        seg_map50: 0.81,
        seg_map: 0.72,
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
        version: "nail-texture-seg-v2",
        inputSize: 640,
        task: "segment",
        backendPreferences: ["webgpu", "wasm"],
        modelFile: "nail-texture-seg-v2.onnx",
        labels: ["nail_texture"],
      },
      null,
      2
    ),
    "utf8"
  );
  await writeFile(path.join(browserDir, "nail-texture-seg-v2.onnx"), Buffer.alloc(1024), "binary");

  const uiReviewPath = path.join(root, "ui-review.json");
  await writeFile(
    uiReviewPath,
    JSON.stringify(
      {
        version: "nail-real-model-ui-review/v1",
        createdAt: "2026-07-02T00:00:00.000Z",
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

  const compareSummaryPath = path.join(outputDir, "compare-summary.json");
  await writeFile(
    compareSummaryPath,
    JSON.stringify(
      {
        ok: true,
        regressions: [],
        improvements: ["seg_map50 improved by 0.02"],
        warnings: [],
      },
      null,
      2
    ),
    "utf8"
  );

  const releaseTraceDraftPath = path.join(batchRootDir, "release-trace-draft.json");
  const reviewedBatchImportPipelineReportPath = path.join(
    batchRootDir,
    "reviewed-batch-import-pipeline-report.json"
  );
  const handoffPath = path.join(batchRootDir, "reviewed-batch-release-handoff.json");

  await writeFile(
    releaseTraceDraftPath,
    JSON.stringify(
      {
        draft: true,
        batch: {
          rootDir: batchRootDir,
          sourceGroup: "seed-batch-030",
          datasetRoot: "C:/tmp/dataset",
          reviewedImportReportPath: "C:/tmp/dataset/metadata/reviewed-import-seed-batch-030.report.json",
          importedFileCount: 4,
        },
      },
      null,
      2
    ),
    "utf8"
  );
  await writeFile(
    reviewedBatchImportPipelineReportPath,
    JSON.stringify(
      {
        ok: true,
        rootDir: batchRootDir,
        reportPath: reviewedBatchImportPipelineReportPath,
        steps: [
          {
            name: "import-reviewed-batch",
            stdout: {
              sourceGroup: "seed-batch-030",
              datasetRoot: "C:/tmp/dataset",
              reportPath: "C:/tmp/dataset/metadata/reviewed-import-seed-batch-030.report.json",
              importedDocuments: Array.from({ length: 4 }, (_, index) => ({
                fileName: `sample-00${index + 1}.jpg`,
              })),
            },
          },
        ],
      },
      null,
      2
    ),
    "utf8"
  );
  await writeFile(
    handoffPath,
    JSON.stringify(
      {
        ok: true,
        version: "reviewed-batch-release-handoff/v1",
        rootDir: batchRootDir,
        reviewedBatchImportPipelineReportPath,
        releaseTraceDraftPath,
        governanceHints: {
          reviewedBatchRootDir: batchRootDir,
          reviewedBatchImportPipelineReportPath,
          releaseTraceDraftPath,
        },
      },
      null,
      2
    ),
    "utf8"
  );

  const registryPath = path.join(browserDir, "release-registry.json");
  await writeFile(
    registryPath,
    JSON.stringify(
      {
        currentVersion: "nail-texture-seg-v1",
        releases: [{ version: "nail-texture-seg-v1" }],
      },
      null,
      2
    ),
    "utf8"
  );

  const historyManifestPath = path.join(outputDir, "release-history-manifest.json");
  const auditOutputDir = path.join(outputDir, "real-model-final-audit");
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
      "--run-governance",
      "--governance-compare-summary",
      compareSummaryPath,
      "--governance-registry",
      registryPath,
      "--governance-reviewed-batch-release-handoff",
      handoffPath,
      "--governance-history-manifest",
      historyManifestPath,
    ],
    { cwd: path.resolve(".") }
  );

  const report = JSON.parse(stdout) as {
    ok: boolean;
    options: {
      governanceReviewedBatchReleaseHandoff: string | null;
      governanceReviewedBatchRootDir: string | null;
      governanceReleaseTraceDraft: string | null;
      governanceReviewedBatchImportPipelineReport: string | null;
    };
  };
  assert.equal(report.ok, true);
  assert.equal(report.options.governanceReviewedBatchReleaseHandoff, handoffPath);
  assert.equal(report.options.governanceReviewedBatchRootDir, batchRootDir);
  assert.equal(report.options.governanceReleaseTraceDraft, releaseTraceDraftPath);
  assert.equal(
    report.options.governanceReviewedBatchImportPipelineReport,
    reviewedBatchImportPipelineReportPath
  );
});

test("run-training-release-pipeline can use governance default paths when handoff is provided", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-train-pipeline-governance-defaults-"));
  const outputDir = path.join(root, "model", "exports", "nail-texture-seg-v4");
  const browserDir = path.join(root, "public", "models", "nail-texture-seg");
  const batchRootDir = path.join(root, "seed-batch-040");
  await mkdir(outputDir, { recursive: true });
  await mkdir(browserDir, { recursive: true });
  await mkdir(batchRootDir, { recursive: true });

  await writeFile(
    path.join(outputDir, "metrics.json"),
    JSON.stringify(
      {
        dataset_yaml: "model/training/dataset.yaml",
        dataset_root: "model/datasets/nail-texture-v1",
        weights: "model/exports/nail-texture-seg-v4/nail-texture-seg-v4/weights/best.pt",
        output: "model/exports/nail-texture-seg-v4/metrics.json",
        split: "test",
        imgsz: 640,
        device: "auto",
        dry_run: false,
        box_map50: 0.92,
        box_map: 0.84,
        seg_map50: 0.82,
        seg_map: 0.73,
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
        version: "nail-texture-seg-v4",
        inputSize: 640,
        task: "segment",
        backendPreferences: ["webgpu", "wasm"],
        modelFile: "nail-texture-seg-v4.onnx",
        labels: ["nail_texture"],
      },
      null,
      2
    ),
    "utf8"
  );
  await writeFile(path.join(browserDir, "nail-texture-seg-v4.onnx"), Buffer.alloc(1024), "binary");

  const uiReviewPath = path.join(root, "ui-review.json");
  await writeFile(
    uiReviewPath,
    JSON.stringify(
      {
        version: "nail-real-model-ui-review/v1",
        createdAt: "2026-07-02T00:00:00.000Z",
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

  const defaultCompareSummaryPath = path.join(outputDir, "compare-summary.json");
  await writeFile(
    defaultCompareSummaryPath,
    JSON.stringify(
      {
        ok: true,
        regressions: [],
        improvements: ["seg_map50 improved by 0.03"],
        warnings: [],
      },
      null,
      2
    ),
    "utf8"
  );

  const releaseTraceDraftPath = path.join(batchRootDir, "release-trace-draft.json");
  const reviewedBatchImportPipelineReportPath = path.join(
    batchRootDir,
    "reviewed-batch-import-pipeline-report.json"
  );
  const handoffPath = path.join(batchRootDir, "reviewed-batch-release-handoff.json");

  await writeFile(
    releaseTraceDraftPath,
    JSON.stringify(
      {
        draft: true,
        batch: {
          rootDir: batchRootDir,
          sourceGroup: "seed-batch-040",
          datasetRoot: "C:/tmp/dataset",
          reviewedImportReportPath: "C:/tmp/dataset/metadata/reviewed-import-seed-batch-040.report.json",
          importedFileCount: 5,
        },
      },
      null,
      2
    ),
    "utf8"
  );
  await writeFile(
    reviewedBatchImportPipelineReportPath,
    JSON.stringify(
      {
        ok: true,
        rootDir: batchRootDir,
        reportPath: reviewedBatchImportPipelineReportPath,
        steps: [
          {
            name: "import-reviewed-batch",
            stdout: {
              sourceGroup: "seed-batch-040",
              datasetRoot: "C:/tmp/dataset",
              reportPath: "C:/tmp/dataset/metadata/reviewed-import-seed-batch-040.report.json",
              importedDocuments: Array.from({ length: 5 }, (_, index) => ({
                fileName: `sample-00${index + 1}.jpg`,
              })),
            },
          },
        ],
      },
      null,
      2
    ),
    "utf8"
  );
  await writeFile(
    handoffPath,
    JSON.stringify(
      {
        ok: true,
        version: "reviewed-batch-release-handoff/v1",
        rootDir: batchRootDir,
        reviewedBatchImportPipelineReportPath,
        releaseTraceDraftPath,
        governanceHints: {
          reviewedBatchRootDir: batchRootDir,
          reviewedBatchImportPipelineReportPath,
          releaseTraceDraftPath,
        },
      },
      null,
      2
    ),
    "utf8"
  );

  const defaultRegistryPath = path.join(browserDir, "release-registry.json");
  await writeFile(
    defaultRegistryPath,
    JSON.stringify(
      {
        currentVersion: "nail-texture-seg-v3",
        releases: [{ version: "nail-texture-seg-v3" }],
      },
      null,
      2
    ),
    "utf8"
  );

  const defaultHistoryManifestPath = path.join(outputDir, "release-history-manifest.json");
  const auditOutputDir = path.join(outputDir, "real-model-final-audit");
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
      "--model-version",
      "nail-texture-seg-v4",
      "--skip-train",
      "--skip-evaluate",
      "--skip-export",
      "--final-audit-image",
      imagePath,
      "--final-audit-output-dir",
      auditOutputDir,
      "--final-audit-ui-review",
      uiReviewPath,
      "--run-governance",
      "--governance-reviewed-batch-release-handoff",
      handoffPath
    ],
    { cwd: path.resolve(".") }
  );

  const report = JSON.parse(stdout) as {
    ok: boolean;
    options: {
      governanceCompareSummary: string | null;
      governanceRegistry: string | null;
      governanceHistoryManifest: string | null;
    };
    artifacts: {
      releaseGovernance: { ok: boolean } | null;
    };
  };
  assert.equal(report.ok, true);
  assert.equal(report.options.governanceCompareSummary, defaultCompareSummaryPath);
  assert.equal(report.options.governanceRegistry, defaultRegistryPath);
  assert.equal(report.options.governanceHistoryManifest, defaultHistoryManifestPath);
  assert.equal(report.artifacts.releaseGovernance?.ok, true);
});
