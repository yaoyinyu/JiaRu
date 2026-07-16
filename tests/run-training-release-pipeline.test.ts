import assert from "node:assert/strict";
import { execFile } from "node:child_process";
import { mkdtemp, mkdir, readFile, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { promisify } from "node:util";
import test from "node:test";

const execFileAsync = promisify(execFile);

async function registerBaselineRelease(modelDir: string, registryPath: string, version: string) {
  const manifestPath = path.join(modelDir, "manifest.json");
  const currentManifest = await readFile(manifestPath, "utf8");
  const modelFile = `${version}.onnx`;
  await writeFile(
    manifestPath,
    JSON.stringify(
      {
        version,
        inputSize: 640,
        task: "segment",
        backendPreferences: ["webgpu", "wasm"],
        modelFile,
        labels: ["nail_texture"],
      },
      null,
      2
    ),
    "utf8"
  );
  await writeFile(path.join(modelDir, modelFile), Buffer.alloc(300 * 1024), "binary");
  await execFileAsync(
    process.execPath,
    [
      "--no-warnings",
      "--experimental-strip-types",
      "scripts/register-model-release.ts",
      "--manifest",
      manifestPath,
      "--registry",
      registryPath,
    ],
    { cwd: path.resolve(".") }
  );
  await writeFile(manifestPath, currentManifest, "utf8");
}

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
    options: { trainingIntent: string; candidateValidationReport: string | null };
    steps: Array<{ name: string; ok: boolean; stdout?: { skipped?: boolean }; command: string[] }>;
  };
  assert.equal(report.ok, true);
  assert.equal(report.mode, "dry-run");
  assert.equal(report.options.trainingIntent, "experiment");
  assert.equal(report.options.candidateValidationReport, null);
  assert.deepEqual(report.steps.map((step) => step.name), [
    "check-training-environment",
    "train-yolo-seg",
    "evaluate",
    "export-onnx",
    "verify-training-release",
    "run-real-model-final-audit",
  ]);
  const preflightStep = report.steps.find((step) => step.name === "check-training-environment");
  assert.ok(preflightStep?.command.includes("model/training/check-training-environment.py"));
  const evaluateStep = report.steps.find((step) => step.name === "evaluate");
  assert.ok(evaluateStep?.command.includes("--artifacts-dir"));
  assert.ok(evaluateStep?.command.some((item) => item.endsWith("evaluation-artifacts")));
  assert.equal(report.steps.at(-1)?.stdout?.skipped, true);
});

test("run-training-release-pipeline requires and forwards candidate validation evidence", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-train-pipeline-candidate-"));
  const outputDir = path.join(root, "model", "exports", "candidate");
  const browserDir = path.join(root, "public", "models", "nail-texture-seg");
  const rejectedReport = path.join(root, "candidate-validation.json");
  await mkdir(outputDir, { recursive: true });
  await mkdir(browserDir, { recursive: true });
  await writeFile(
    rejectedReport,
    JSON.stringify({
      ok: false,
      decision: "rejected_candidate_training_validation",
      candidateTrainingEligible: false,
    }),
    "utf8"
  );

  await assert.rejects(
    execFileAsync(
      process.execPath,
      [
        "--no-warnings",
        "--experimental-strip-types",
        "scripts/run-training-release-pipeline.ts",
        "--candidate-mode",
        "--dry-run",
      ],
      { cwd: path.resolve(".") }
    ),
    /--candidate-mode requires --candidate-validation-report/
  );

  let caught: unknown;
  try {
    await execFileAsync(
      process.execPath,
      [
        "--no-warnings",
        "--experimental-strip-types",
        "scripts/run-training-release-pipeline.ts",
        "--train-output-dir",
        outputDir,
        "--browser-model-dir",
        browserDir,
        "--candidate-mode",
        "--candidate-validation-report",
        rejectedReport,
        "--skip-training-environment-check",
        "--dry-run",
      ],
      { cwd: path.resolve(".") }
    );
  } catch (error) {
    caught = error;
  }
  assert.ok(caught, "rejected candidate evidence must stop the pipeline");
  const report = JSON.parse((caught as { stdout?: string }).stdout ?? "") as {
    ok: boolean;
    options: { trainingIntent: string; candidateValidationReport: string | null };
    steps: Array<{ name: string; command: string[] }>;
  };
  assert.equal(report.ok, false);
  assert.equal(report.options.trainingIntent, "candidate");
  assert.equal(report.options.candidateValidationReport, rejectedReport);
  assert.deepEqual(report.steps.map((step) => step.name), ["train-yolo-seg"]);
  assert.ok(report.steps[0]?.command.includes("--candidate-mode"));
  assert.ok(report.steps[0]?.command.includes(rejectedReport));
});


test("run-training-release-pipeline can skip training environment preflight", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-train-pipeline-skip-env-"));
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
      "--skip-training-environment-check",
    ],
    { cwd: path.resolve(".") }
  );

  const report = JSON.parse(stdout) as {
    ok: boolean;
    options: { skipTrainingEnvironmentCheck: boolean };
    steps: Array<{ name: string }>;
  };
  assert.equal(report.ok, true);
  assert.equal(report.options.skipTrainingEnvironmentCheck, true);
  assert.ok(!report.steps.some((step) => step.name === "check-training-environment"));
});

test("run-training-release-pipeline forwards local checkpoint requirement to preflight", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-train-pipeline-require-local-"));
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
      "--require-local-model",
    ],
    { cwd: path.resolve(".") }
  );

  const report = JSON.parse(stdout) as {
    ok: boolean;
    options: { requireLocalModel: boolean };
    steps: Array<{ name: string; command: string[] }>;
  };
  const preflightStep = report.steps.find((step) => step.name === "check-training-environment");
  assert.equal(report.ok, true);
  assert.equal(report.options.requireLocalModel, true);
  assert.ok(preflightStep?.command.includes("--require-local-model"));
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


test("run-training-release-pipeline blocks real training before python when source authorization is missing", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-train-pipeline-source-auth-missing-"));
  const outputDir = path.join(root, "model", "exports", "nail-texture-seg-v1");
  const browserDir = path.join(root, "public", "models", "nail-texture-seg");
  const datasetRoot = path.join(root, "model", "datasets", "nail-texture-v1");
  await mkdir(outputDir, { recursive: true });
  await mkdir(browserDir, { recursive: true });
  await mkdir(path.join(datasetRoot, "metadata"), { recursive: true });

  let caught: unknown;
  try {
    await execFileAsync(
      process.execPath,
      [
        "--no-warnings",
        "--experimental-strip-types",
        "scripts/run-training-release-pipeline.ts",
        "--train-output-dir",
        outputDir,
        "--browser-model-dir",
        browserDir,
        "--source-authorization-dataset-root",
        datasetRoot,
      ],
      { cwd: path.resolve(".") }
    );
  } catch (error) {
    caught = error;
  }

  assert.ok(caught, "pipeline should fail before training when source authorization is missing");
  const stdout = (caught as { stdout?: string }).stdout ?? "";
  const report = JSON.parse(stdout) as {
    ok: boolean;
    steps: Array<{ name: string; ok: boolean; command: string[]; stdout?: unknown; stderr?: string }>;
    options: { sourceAuthorizationDatasetRoot: string; skipSourceAuthorization: boolean };
  };
  assert.equal(report.ok, false);
  assert.equal(report.options.sourceAuthorizationDatasetRoot, datasetRoot);
  assert.equal(report.options.skipSourceAuthorization, false);
  assert.deepEqual(report.steps.map((step) => step.name), ["verify-training-dataset-readiness"]);
  assert.equal(report.steps[0]?.ok, false);
  assert.ok(report.steps[0]?.command.includes("model/training/verify-training-dataset-readiness.ts"));
  const readinessStdout = report.steps[0]?.stdout as { steps?: Array<{ name: string; ok: boolean }> } | undefined;
  assert.deepEqual(readinessStdout?.steps?.map((step) => step.name), [
    "audit-sources-csv",
    "audit-training-source-authorization",
    "audit-phase1-readiness",
  ]);
  assert.ok(readinessStdout?.steps?.some((step) => !step.ok));

  const persisted = JSON.parse(
    await readFile(path.join(outputDir, "training-release-pipeline-report.json"), "utf8")
  ) as { ok: boolean; steps: Array<{ name: string }> };
  assert.equal(persisted.ok, false);
  assert.deepEqual(persisted.steps.map((step) => step.name), ["verify-training-dataset-readiness"]);
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
        modelSizeBytes: 307200,
        sha256: "7818f5542a0404157573be6cffc0e0c8e68ce3c0f5d17d07ccdd9313fb700baf",
        labels: ["nail_texture"],
      },
      null,
      2
    ),
    "utf8"
  );
  await writeFile(path.join(browserDir, "nail-texture-seg-v1.onnx"), Buffer.alloc(300 * 1024), "binary");

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
        modelSizeBytes: 307200,
        sha256: "7818f5542a0404157573be6cffc0e0c8e68ce3c0f5d17d07ccdd9313fb700baf",
        labels: ["nail_texture"],
      },
      null,
      2
    ),
    "utf8"
  );
  await writeFile(path.join(browserDir, "nail-texture-seg-v1.onnx"), Buffer.alloc(300 * 1024), "binary");

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
        modelSizeBytes: 307200,
        sha256: "7818f5542a0404157573be6cffc0e0c8e68ce3c0f5d17d07ccdd9313fb700baf",
        labels: ["nail_texture"],
      },
      null,
      2
    ),
    "utf8"
  );
  await writeFile(path.join(browserDir, "nail-texture-seg-v1.onnx"), Buffer.alloc(300 * 1024), "binary");

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
      finalAuditTextureQualityGate: {
        ok: boolean;
        rates: { directlyUsableRate: number | null; contaminationRate: number | null };
      } | null;
    };
  };
  assert.equal(report.ok, true);
  assert.equal(report.options.finalAuditAnnotationDir, annotationDir);
  assert.equal(report.artifacts.finalAudit.annotationDirPath, annotationDir);
  assert.equal(report.artifacts.finalAuditFailureSummary.totals.derivedAnnotationFailures, 3);
  assert.equal(report.artifacts.finalAuditFailureSummary.categoryCounts.postprocess, 3);
  assert.equal(report.artifacts.finalAuditTextureQualityGate?.ok, false);
  assert.equal(report.artifacts.finalAuditTextureQualityGate?.rates.directlyUsableRate, 0);
  assert.equal(report.artifacts.finalAuditTextureQualityGate?.rates.contaminationRate, 0);
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
        modelSizeBytes: 307200,
        sha256: "7818f5542a0404157573be6cffc0e0c8e68ce3c0f5d17d07ccdd9313fb700baf",
        labels: ["nail_texture"],
      },
      null,
      2
    ),
    "utf8"
  );
  await writeFile(path.join(browserDir, "nail-texture-seg-v2.onnx"), Buffer.alloc(300 * 1024), "binary");

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

  const performanceReportPath = path.join(outputDir, "performance-report.mobile.json");
  await writeFile(
    performanceReportPath,
    JSON.stringify(
      {
        ok: true,
        profile: "mobile",
        thresholds: { maxElapsedMs: 1500, minSamples: 3 },
        totals: { samples: 3, slowSamples: 0, skippedFiles: 0 },
        stats: { averageMs: 860, p50Ms: 840, p95Ms: 980, maxMs: 980 },
        errors: [],
        warnings: [],
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
  await registerBaselineRelease(browserDir, registryPath, "nail-texture-seg-v1");

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
      "--governance-performance-report",
      performanceReportPath,
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
    options: {
      runGovernance: boolean;
      governanceCompareSummary: string | null;
      governancePerformanceReport: string | null;
    };
    paths: { governanceReportPath: string | null };
    artifacts: {
      recognitionPerformance: { ok: boolean; profile: string } | null;
      releaseGovernance: {
        ok: boolean;
        artifacts: {
          releaseDecision: {
            decision: { status: string };
            inputs: { recognitionPerformanceOk: boolean | null; recognitionPerformanceP95Ms: number | null };
          };
          traceIndex: {
            performance: { ok: boolean | null; profile: string | null; p95Ms: number | null } | null;
          };
          promotion: { registerSummary: { registeredVersion: string } };
          historyManifest: { totals: { traceIndexes: number } };
        };
      } | null;
    };
  };
  assert.equal(report.ok, true);
  assert.equal(report.options.runGovernance, true);
  assert.equal(report.options.governanceCompareSummary, compareSummaryPath);
  assert.equal(report.options.governancePerformanceReport, performanceReportPath);
  assert.equal(report.artifacts.recognitionPerformance?.ok, true);
  assert.equal(report.artifacts.recognitionPerformance?.profile, "mobile");
  assert.equal(report.steps.at(-1)?.name, "run-release-governance-pipeline");
  assert.equal(report.steps.at(-1)?.ok, true);
  assert.ok(report.paths.governanceReportPath);
  assert.equal(report.artifacts.releaseGovernance?.ok, true);
  assert.equal(
    report.artifacts.releaseGovernance?.artifacts.releaseDecision.decision.status,
    "approve_candidate"
  );
  assert.equal(
    report.artifacts.releaseGovernance?.artifacts.releaseDecision.inputs.recognitionPerformanceOk,
    true
  );
  assert.equal(
    report.artifacts.releaseGovernance?.artifacts.releaseDecision.inputs.recognitionPerformanceP95Ms,
    980
  );
  assert.equal(
    report.artifacts.releaseGovernance?.artifacts.traceIndex.performance?.ok,
    true
  );
  assert.equal(
    report.artifacts.releaseGovernance?.artifacts.traceIndex.performance?.profile,
    "mobile"
  );
  assert.equal(
    report.artifacts.releaseGovernance?.artifacts.traceIndex.performance?.p95Ms,
    980
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
        modelSizeBytes: 307200,
        sha256: "7818f5542a0404157573be6cffc0e0c8e68ce3c0f5d17d07ccdd9313fb700baf",
        labels: ["nail_texture"],
      },
      null,
      2
    ),
    "utf8"
  );
  await writeFile(path.join(browserDir, "nail-texture-seg-v2.onnx"), Buffer.alloc(300 * 1024), "binary");

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

  const performanceReportPath = path.join(outputDir, "performance-report.mobile.json");
  await writeFile(
    performanceReportPath,
    JSON.stringify(
      {
        ok: true,
        profile: "mobile",
        thresholds: { maxElapsedMs: 1500, minSamples: 3 },
        totals: { samples: 3, slowSamples: 0, skippedFiles: 0 },
        stats: { averageMs: 860, p50Ms: 840, p95Ms: 980, maxMs: 980 },
        errors: [],
        warnings: [],
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
  await registerBaselineRelease(browserDir, registryPath, "nail-texture-seg-v1");

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
      "--governance-performance-report",
      performanceReportPath,
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
      recognitionPerformance: { ok: boolean; profile: string } | null;
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
        modelSizeBytes: 307200,
        sha256: "7818f5542a0404157573be6cffc0e0c8e68ce3c0f5d17d07ccdd9313fb700baf",
        labels: ["nail_texture"],
      },
      null,
      2
    ),
    "utf8"
  );
  await writeFile(path.join(browserDir, "nail-texture-seg-v2.onnx"), Buffer.alloc(300 * 1024), "binary");

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

  const performanceReportPath = path.join(outputDir, "performance-report.mobile.json");
  await writeFile(
    performanceReportPath,
    JSON.stringify(
      {
        ok: true,
        profile: "mobile",
        thresholds: { maxElapsedMs: 1500, minSamples: 3 },
        totals: { samples: 3, slowSamples: 0, skippedFiles: 0 },
        stats: { averageMs: 860, p50Ms: 840, p95Ms: 980, maxMs: 980 },
        errors: [],
        warnings: [],
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
  await registerBaselineRelease(browserDir, registryPath, "nail-texture-seg-v1");

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
      "--governance-performance-report",
      performanceReportPath,
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
        modelSizeBytes: 307200,
        sha256: "7818f5542a0404157573be6cffc0e0c8e68ce3c0f5d17d07ccdd9313fb700baf",
        labels: ["nail_texture"],
      },
      null,
      2
    ),
    "utf8"
  );
  await writeFile(path.join(browserDir, "nail-texture-seg-v4.onnx"), Buffer.alloc(300 * 1024), "binary");

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
  await registerBaselineRelease(browserDir, defaultRegistryPath, "nail-texture-seg-v3");

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
      recognitionPerformance: { ok: boolean; profile: string } | null;
      releaseGovernance: { ok: boolean } | null;
    };
  };
  assert.equal(report.ok, true);
  assert.equal(report.options.governanceCompareSummary, defaultCompareSummaryPath);
  assert.equal(report.options.governanceRegistry, defaultRegistryPath);
  assert.equal(report.options.governanceHistoryManifest, defaultHistoryManifestPath);
  assert.equal(report.artifacts.releaseGovernance?.ok, true);
});

test("run-training-release-pipeline can consume active learning handoff for governance trace context", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-train-pipeline-active-learning-handoff-"));
  const outputDir = path.join(root, "model", "exports", "nail-texture-seg-v5");
  const browserDir = path.join(root, "public", "models", "nail-texture-seg");
  const activeLearningDir = path.join(root, "active-learning");
  await mkdir(outputDir, { recursive: true });
  await mkdir(browserDir, { recursive: true });
  await mkdir(activeLearningDir, { recursive: true });

  await writeFile(
    path.join(outputDir, "metrics.json"),
    JSON.stringify(
      {
        dataset_yaml: "model/training/dataset.yaml",
        dataset_root: "model/datasets/nail-texture-v1",
        weights: "model/exports/nail-texture-seg-v5/nail-texture-seg-v5/weights/best.pt",
        output: "model/exports/nail-texture-seg-v5/metrics.json",
        split: "test",
        imgsz: 640,
        device: "auto",
        dry_run: false,
        box_map50: 0.93,
        box_map: 0.85,
        seg_map50: 0.83,
        seg_map: 0.74,
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
        version: "nail-texture-seg-v5",
        inputSize: 640,
        task: "segment",
        backendPreferences: ["webgpu", "wasm"],
        modelFile: "nail-texture-seg-v5.onnx",
        modelSizeBytes: 307200,
        sha256: "7818f5542a0404157573be6cffc0e0c8e68ce3c0f5d17d07ccdd9313fb700baf",
        labels: ["nail_texture"],
      },
      null,
      2
    ),
    "utf8"
  );
  await writeFile(path.join(browserDir, "nail-texture-seg-v5.onnx"), Buffer.alloc(300 * 1024), "binary");

  const uiReviewPath = path.join(root, "ui-review.json");
  await writeFile(
    uiReviewPath,
    JSON.stringify(
      {
        version: "nail-real-model-ui-review/v1",
        createdAt: "2026-07-03T00:00:00.000Z",
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

  const performanceReportPath = path.join(outputDir, "performance-report.mobile.json");
  await writeFile(
    performanceReportPath,
    JSON.stringify(
      {
        ok: true,
        profile: "mobile",
        thresholds: { maxElapsedMs: 1500, minSamples: 3 },
        totals: { samples: 3, slowSamples: 0, skippedFiles: 0 },
        stats: { averageMs: 860, p50Ms: 840, p95Ms: 980, maxMs: 980 },
        errors: [],
        warnings: [],
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
        improvements: ["seg_map50 improved by 0.04"],
        warnings: [],
      },
      null,
      2
    ),
    "utf8"
  );

  const activeLearningReleaseTraceDraftPath = path.join(
    activeLearningDir,
    "active-learning-release-trace-draft.json"
  );
  await writeFile(
    activeLearningReleaseTraceDraftPath,
    JSON.stringify(
      {
        draft: true,
        activeLearning: {
          pipelineReportPath: path.join(activeLearningDir, "debug-sample-active-learning-pipeline-report.json"),
          sampleDir: path.join(activeLearningDir, "samples"),
          imageDir: path.join(activeLearningDir, "images"),
          priorityReportPath: path.join(activeLearningDir, "prioritized-debug-samples.json"),
          priorityFilters: {
            reportPath: path.join(activeLearningDir, "prioritized-debug-samples.json"),
            minPriorityTier: "medium",
            top: 20,
          },
          importedSampleCount: 5,
          importedByPriority: {
            high: 3,
            medium: 2,
            low: 0,
            unknown: 0,
          },
          prioritySummary: {
            backendBreakdown: { fallback: 4, model: 1 },
            modelBackendBreakdown: { fallback: 4, wasm: 1 },
            correctedCandidateSourceBreakdown: { manual: 3, model: 2 },
            warningBreakdown: { onnx_runtime_not_loaded: 2, model_inference_error: 1 },
            reasonBreakdown: { manual_candidate_added: 3, high_confidence_deleted: 1 },
          },
          readinessSnapshot: {
            reportPath: path.join(activeLearningDir, "phase1-readiness.json"),
            imageCountGate: { ok: false, actual: 25, required: 200 },
            validMaskCountGate: { ok: false, actual: 90, required: 800 },
            totals: { images: 25, validMasks: 90 },
          },
        },
      },
      null,
      2
    ),
    "utf8"
  );

  const activeLearningHandoffPath = path.join(
    activeLearningDir,
    "debug-sample-active-learning-handoff.json"
  );
  await writeFile(
    activeLearningHandoffPath,
    JSON.stringify(
      {
        ok: true,
        version: "debug-sample-active-learning-handoff/v1",
        pipelineReportPath: path.join(activeLearningDir, "debug-sample-active-learning-pipeline-report.json"),
        releaseTraceDraftPath: activeLearningReleaseTraceDraftPath,
        activeLearning: {
          importedSampleCount: 5,
        },
        governanceHints: {
          activeLearningPipelineReportPath: path.join(
            activeLearningDir,
            "debug-sample-active-learning-pipeline-report.json"
          ),
          activeLearningReleaseTraceDraftPath,
        },
      },
      null,
      2
    ),
    "utf8"
  );

  const registryPath = path.join(browserDir, "release-registry.json");
  await registerBaselineRelease(browserDir, registryPath, "nail-texture-seg-v4");

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
      "--model-version",
      "nail-texture-seg-v5",
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
      "--governance-performance-report",
      performanceReportPath,
      "--governance-registry",
      registryPath,
      "--governance-active-learning-handoff",
      activeLearningHandoffPath,
      "--governance-history-manifest",
      historyManifestPath,
    ],
    { cwd: path.resolve(".") }
  );

  const report = JSON.parse(stdout) as {
    ok: boolean;
    options: {
      governanceActiveLearningHandoff: string | null;
      governanceReleaseTraceDraft: string | null;
    };
    artifacts: {
      recognitionPerformance: { ok: boolean; profile: string } | null;
      releaseGovernance: {
        ok: boolean;
        artifacts: {
          traceIndex: {
            activeLearning: {
              importedSampleCount: number;
              importedByPriority: { high: number; medium: number };
              prioritySummary: {
                backendBreakdown: Record<string, number>;
                warningBreakdown: Record<string, number>;
              } | null;
            } | null;
          };
        };
      } | null;
    };
  };

  assert.equal(report.ok, true);
  assert.equal(report.options.governanceActiveLearningHandoff, activeLearningHandoffPath);
  assert.equal(report.options.governanceReleaseTraceDraft, activeLearningReleaseTraceDraftPath);
  assert.equal(report.artifacts.releaseGovernance?.ok, true);
  assert.equal(
    report.artifacts.releaseGovernance?.artifacts.traceIndex.activeLearning?.importedSampleCount,
    5
  );
  assert.equal(
    report.artifacts.releaseGovernance?.artifacts.traceIndex.activeLearning?.importedByPriority.high,
    3
  );
  assert.equal(
    report.artifacts.releaseGovernance?.artifacts.traceIndex.activeLearning?.importedByPriority.medium,
    2
  );
  assert.deepEqual(
    report.artifacts.releaseGovernance?.artifacts.traceIndex.activeLearning?.prioritySummary?.backendBreakdown,
    { fallback: 4, model: 1 }
  );
  assert.deepEqual(
    report.artifacts.releaseGovernance?.artifacts.traceIndex.activeLearning?.prioritySummary?.warningBreakdown,
    { onnx_runtime_not_loaded: 2, model_inference_error: 1 }
  );
});

test("run-training-release-pipeline can promote active-learning warning manual reviews when explicitly allowed", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-train-pipeline-active-learning-warning-allow-"));
  const outputDir = path.join(root, "model", "exports", "nail-texture-seg-v6");
  const browserDir = path.join(root, "public", "models", "nail-texture-seg");
  await mkdir(outputDir, { recursive: true });
  await mkdir(browserDir, { recursive: true });

  await writeFile(
    path.join(outputDir, "metrics.json"),
    JSON.stringify(
      {
        dataset_yaml: "model/training/dataset.yaml",
        dataset_root: "model/datasets/nail-texture-v1",
        weights: "model/exports/nail-texture-seg-v6/nail-texture-seg-v6/weights/best.pt",
        output: "model/exports/nail-texture-seg-v6/metrics.json",
        split: "test",
        imgsz: 640,
        device: "auto",
        dry_run: false,
        box_map50: 0.94,
        box_map: 0.86,
        seg_map50: 0.84,
        seg_map: 0.75,
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
        version: "nail-texture-seg-v6",
        inputSize: 640,
        task: "segment",
        backendPreferences: ["webgpu", "wasm"],
        modelFile: "nail-texture-seg-v6.onnx",
        modelSizeBytes: 307200,
        sha256: "7818f5542a0404157573be6cffc0e0c8e68ce3c0f5d17d07ccdd9313fb700baf",
        labels: ["nail_texture"],
      },
      null,
      2
    ),
    "utf8"
  );
  await writeFile(path.join(browserDir, "nail-texture-seg-v6.onnx"), Buffer.alloc(300 * 1024), "binary");

  const compareSummaryPath = path.join(outputDir, "compare-summary.json");
  await writeFile(
    compareSummaryPath,
    JSON.stringify(
      {
        ok: true,
        regressions: [],
        improvements: ["seg_map50 improved by 0.05"],
        warnings: ["active-learning warning signals increased by 2"],
        deltas: {
          activeLearningImportedSamples: 3,
          activeLearningWarnings: {
            model_inference_error: 2,
            onnx_runtime_not_loaded: -1,
          },
          activeLearningBackends: {
            model: 3,
            fallback: -1,
          },
        },
      },
      null,
      2
    ),
    "utf8"
  );

  const registryPath = path.join(browserDir, "release-registry.json");
  await registerBaselineRelease(browserDir, registryPath, "nail-texture-seg-v5");

  const historyManifestPath = path.join(outputDir, "release-history-manifest.json");
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
      "nail-texture-seg-v6",
      "--skip-train",
      "--skip-evaluate",
      "--skip-export",
      "--run-governance",
      "--governance-compare-summary",
      compareSummaryPath,
      "--governance-registry",
      registryPath,
      "--governance-history-manifest",
      historyManifestPath,
      "--governance-allow-manual-review",
      "true",
    ],
    { cwd: path.resolve(".") }
  );

  const report = JSON.parse(stdout) as {
    ok: boolean;
    options: { governanceAllowManualReview: boolean };
    artifacts: {
      releaseGovernance: {
        ok: boolean;
        artifacts: {
          releaseDecision: {
            decision: { status: string; reasons: string[] };
            inputs: {
              activeLearningWarningDelta: number;
              activeLearningWarningDeltas: Record<string, number>;
            };
          };
          promotion: {
            ok: boolean;
            decisionStatus: string;
            registerSummary: { registeredVersion: string };
          };
          traceRegistration: { ok: boolean };
          rollbackAudit: { ok: boolean; rollbackCandidates: string[] };
          historyManifest: { totals: { traceIndexes: number }; entries: Array<{ decisionStatus: string }> };
        };
      } | null;
    };
  };

  assert.equal(report.ok, true);
  assert.equal(report.options.governanceAllowManualReview, true);
  assert.equal(report.artifacts.releaseGovernance?.ok, true);
  assert.equal(report.artifacts.releaseGovernance?.artifacts.releaseDecision.decision.status, "manual_review");
  assert.ok(
    report.artifacts.releaseGovernance?.artifacts.releaseDecision.decision.reasons.includes(
      "active-learning warning signals increased by 2"
    )
  );
  assert.equal(
    report.artifacts.releaseGovernance?.artifacts.releaseDecision.inputs.activeLearningWarningDelta,
    2
  );
  assert.deepEqual(
    report.artifacts.releaseGovernance?.artifacts.releaseDecision.inputs.activeLearningWarningDeltas,
    {
      model_inference_error: 2,
      onnx_runtime_not_loaded: -1,
    }
  );
  assert.equal(report.artifacts.releaseGovernance?.artifacts.promotion.ok, true);
  assert.equal(report.artifacts.releaseGovernance?.artifacts.promotion.decisionStatus, "manual_review");
  assert.equal(
    report.artifacts.releaseGovernance?.artifacts.promotion.registerSummary.registeredVersion,
    "nail-texture-seg-v6"
  );
  assert.equal(report.artifacts.releaseGovernance?.artifacts.traceRegistration.ok, true);
  assert.equal(report.artifacts.releaseGovernance?.artifacts.rollbackAudit.ok, true);
  assert.deepEqual(report.artifacts.releaseGovernance?.artifacts.rollbackAudit.rollbackCandidates, [
    "nail-texture-seg-v5",
  ]);
  assert.equal(report.artifacts.releaseGovernance?.artifacts.historyManifest.totals.traceIndexes, 1);
  assert.equal(
    report.artifacts.releaseGovernance?.artifacts.historyManifest.entries[0]?.decisionStatus,
    "manual_review"
  );
});
test("run-training-release-pipeline can promote visual evidence manual reviews when explicitly allowed", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-train-pipeline-visual-evidence-allow-"));
  const outputDir = path.join(root, "model", "exports", "nail-texture-seg-v7");
  const browserDir = path.join(root, "public", "models", "nail-texture-seg");
  await mkdir(outputDir, { recursive: true });
  await mkdir(browserDir, { recursive: true });

  await writeFile(
    path.join(outputDir, "metrics.json"),
    JSON.stringify(
      {
        dataset_yaml: "model/training/dataset.yaml",
        dataset_root: "model/datasets/nail-texture-v1",
        weights: "model/exports/nail-texture-seg-v7/nail-texture-seg-v7/weights/best.pt",
        output: "model/exports/nail-texture-seg-v7/metrics.json",
        split: "test",
        imgsz: 640,
        device: "auto",
        dry_run: false,
        box_map50: 0.94,
        box_map: 0.86,
        seg_map50: 0.84,
        seg_map: 0.75,
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
        version: "nail-texture-seg-v7",
        inputSize: 640,
        task: "segment",
        backendPreferences: ["webgpu", "wasm"],
        modelFile: "nail-texture-seg-v7.onnx",
        modelSizeBytes: 307200,
        sha256: "7818f5542a0404157573be6cffc0e0c8e68ce3c0f5d17d07ccdd9313fb700baf",
        labels: ["nail_texture"],
      },
      null,
      2
    ),
    "utf8"
  );
  await writeFile(path.join(browserDir, "nail-texture-seg-v7.onnx"), Buffer.alloc(300 * 1024), "binary");

  const compareSummaryPath = path.join(outputDir, "compare-summary.json");
  await writeFile(
    compareSummaryPath,
    JSON.stringify(
      {
        ok: true,
        regressions: [],
        improvements: ["seg_map50 improved by 0.05"],
        warnings: ["candidate recognition mask visual evidence is missing"],
        deltas: {
          firstRunVisualEvidence: 0,
          recognitionMaskEvidence: -1,
        },
      },
      null,
      2
    ),
    "utf8"
  );

  const registryPath = path.join(browserDir, "release-registry.json");
  await registerBaselineRelease(browserDir, registryPath, "nail-texture-seg-v6");

  const historyManifestPath = path.join(outputDir, "release-history-manifest.json");
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
      "nail-texture-seg-v7",
      "--skip-train",
      "--skip-evaluate",
      "--skip-export",
      "--run-governance",
      "--governance-compare-summary",
      compareSummaryPath,
      "--governance-registry",
      registryPath,
      "--governance-history-manifest",
      historyManifestPath,
      "--governance-allow-manual-review",
      "true",
    ],
    { cwd: path.resolve(".") }
  );

  const report = JSON.parse(stdout) as {
    ok: boolean;
    options: { governanceAllowManualReview: boolean };
    artifacts: {
      releaseGovernance: {
        ok: boolean;
        artifacts: {
          releaseDecision: {
            decision: { status: string; reasons: string[] };
            inputs: {
              firstRunVisualEvidenceDelta: number | null;
              recognitionMaskEvidenceDelta: number | null;
            };
          };
          promotion: {
            ok: boolean;
            decisionStatus: string;
            registerSummary: { registeredVersion: string };
          };
          traceIndex: { decision: { status: string } | null };
          traceRegistration: { ok: boolean };
          rollbackAudit: { ok: boolean; rollbackCandidates: string[] };
          historyManifest: { totals: { traceIndexes: number }; entries: Array<{ decisionStatus: string }> };
        };
      } | null;
    };
  };

  assert.equal(report.ok, true);
  assert.equal(report.options.governanceAllowManualReview, true);
  assert.equal(report.artifacts.releaseGovernance?.ok, true);
  assert.equal(report.artifacts.releaseGovernance?.artifacts.releaseDecision.decision.status, "manual_review");
  assert.ok(
    report.artifacts.releaseGovernance?.artifacts.releaseDecision.decision.reasons.some((item) =>
      item.includes("candidate visual evidence decreased")
    )
  );
  assert.equal(
    report.artifacts.releaseGovernance?.artifacts.releaseDecision.inputs.firstRunVisualEvidenceDelta,
    0
  );
  assert.equal(
    report.artifacts.releaseGovernance?.artifacts.releaseDecision.inputs.recognitionMaskEvidenceDelta,
    -1
  );
  assert.equal(report.artifacts.releaseGovernance?.artifacts.promotion.ok, true);
  assert.equal(report.artifacts.releaseGovernance?.artifacts.promotion.decisionStatus, "manual_review");
  assert.equal(
    report.artifacts.releaseGovernance?.artifacts.promotion.registerSummary.registeredVersion,
    "nail-texture-seg-v7"
  );
  assert.equal(report.artifacts.releaseGovernance?.artifacts.traceIndex.decision?.status, "manual_review");
  assert.equal(report.artifacts.releaseGovernance?.artifacts.traceRegistration.ok, true);
  assert.equal(report.artifacts.releaseGovernance?.artifacts.rollbackAudit.ok, true);
  assert.deepEqual(report.artifacts.releaseGovernance?.artifacts.rollbackAudit.rollbackCandidates, [
    "nail-texture-seg-v6",
  ]);
  assert.equal(report.artifacts.releaseGovernance?.artifacts.historyManifest.totals.traceIndexes, 1);
  assert.equal(
    report.artifacts.releaseGovernance?.artifacts.historyManifest.entries[0]?.decisionStatus,
    "manual_review"
  );
});
