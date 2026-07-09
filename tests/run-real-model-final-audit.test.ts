import assert from "node:assert/strict";
import { execFile } from "node:child_process";
import { mkdtemp, mkdir, readFile, writeFile } from "node:fs/promises";
import { promisify } from "node:util";
import os from "node:os";
import path from "node:path";
import test from "node:test";

const execFileAsync = promisify(execFile);

test("run-real-model-final-audit writes final report and first-run record", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-final-audit-"));
  const modelDir = path.join(root, "public", "models", "nail-texture-seg");
  const exportsDir = path.join(root, "model", "exports", "nail-texture-seg-v1");
  const outputDir = path.join(root, "audit-output");
  await mkdir(modelDir, { recursive: true });
  await mkdir(exportsDir, { recursive: true });
  await mkdir(outputDir, { recursive: true });

  const manifestPath = path.join(modelDir, "manifest.json");
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
  await writeFile(path.join(modelDir, "nail-texture-seg-v1.onnx"), Buffer.alloc(300 * 1024), "binary");

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
  const { stdout } = await execFileAsync(
    process.execPath,
    [
      "--no-warnings",
      "--experimental-strip-types",
      "scripts/run-real-model-final-audit.ts",
      "--manifest",
      manifestPath,
      "--image",
      imagePath,
      "--output-dir",
      outputDir,
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
    finalReportPath: string;
    recordPath: string;
    failureSummaryPath: string;
  };
  const finalReport = JSON.parse(await readFile(summary.finalReportPath, "utf8")) as {
    decision: { status: string };
    failureSummary: { totals: { inferredRecordFailure: number } };
  };
  const firstRunRecord = JSON.parse(await readFile(summary.recordPath, "utf8")) as {
    decision: { status: string };
  };
  const failureSummary = JSON.parse(await readFile(summary.failureSummaryPath, "utf8")) as {
    totals: { inferredRecordFailure: number };
  };

  assert.equal(finalReport.decision.status, "pass");
  assert.equal(firstRunRecord.decision.status, "pass");
  assert.equal(finalReport.failureSummary.totals.inferredRecordFailure, 0);
  assert.equal(finalReport.firstRunOutputs.recognitionMaskPath, firstRunRecord.outputs.recognitionMaskPath);
  assert.match(finalReport.firstRunOutputs.recognitionMaskPath ?? "", /real-model-5188\.jpg_wh860-recognition-mask-overlay\.png$/);
  assert.equal(failureSummary.totals.inferredRecordFailure, 0);
});

test("run-real-model-final-audit reports blocked when model artifact is missing", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-final-audit-blocked-"));
  const modelDir = path.join(root, "public", "models", "nail-texture-seg");
  const outputDir = path.join(root, "audit-output");
  await mkdir(modelDir, { recursive: true });
  await mkdir(outputDir, { recursive: true });

  const manifestPath = path.join(modelDir, "manifest.json");
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

  const imagePath = path.resolve("model/5188.jpg_wh860.jpg");

  try {
    await execFileAsync(
      process.execPath,
      [
        "--no-warnings",
        "--experimental-strip-types",
        "scripts/run-real-model-final-audit.ts",
        "--manifest",
        manifestPath,
        "--image",
        imagePath,
        "--output-dir",
        outputDir,
        "--debug-prefix",
        "real-model",
      ],
      {
        cwd: path.resolve("."),
      }
    );
    assert.fail("expected final audit to exit non-zero when model artifact is missing");
  } catch (error) {
    const execError = error as Error & { stdout?: string };
    const summary = JSON.parse(execError.stdout ?? "{}") as {
      decision: { status: string };
      finalReportPath: string;
      failureSummaryPath: string;
    };
    assert.equal(summary.decision.status, "blocked");
    const savedReport = JSON.parse(await readFile(summary.finalReportPath, "utf8")) as {
      decision: { status: string };
      readiness: { ok: boolean };
      failureSummary: { inferredFromFirstRunRecord: { category: string } | null };
    };
    const failureSummary = JSON.parse(await readFile(summary.failureSummaryPath, "utf8")) as {
      inferredFromFirstRunRecord: { category: string } | null;
      categoryCounts: Record<string, number>;
    };
    assert.equal(savedReport.decision.status, "blocked");
    assert.equal(savedReport.readiness.ok, false);
    assert.equal(savedReport.failureSummary.inferredFromFirstRunRecord?.category, "model");
    assert.equal(failureSummary.inferredFromFirstRunRecord?.category, "model");
    assert.equal(failureSummary.categoryCounts.model, 1);
  }
});

test("run-real-model-final-audit can include annotation debug failures in summary", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-final-audit-annotation-"));
  const modelDir = path.join(root, "public", "models", "nail-texture-seg");
  const outputDir = path.join(root, "audit-output");
  const annotationDir = path.join(root, "annotations");
  const uiReviewPath = path.join(root, "ui-review.json");
  await mkdir(modelDir, { recursive: true });
  await mkdir(outputDir, { recursive: true });
  await mkdir(annotationDir, { recursive: true });

  const manifestPath = path.join(modelDir, "manifest.json");
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

  await writeFile(path.join(modelDir, "nail-texture-seg-v1.onnx"), Buffer.alloc(300 * 1024), "binary");
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

  const imagePath = path.resolve("model/5188.jpg_wh860.jpg");

  const { stdout } = await execFileAsync(
    process.execPath,
    [
      "--no-warnings",
      "--experimental-strip-types",
      "scripts/run-real-model-final-audit.ts",
      "--manifest",
      manifestPath,
      "--image",
      imagePath,
      "--output-dir",
      outputDir,
      "--debug-prefix",
      "real-model",
      "--annotation-dir",
      annotationDir,
      "--ui-review",
      uiReviewPath,
    ],
    {
      cwd: path.resolve("."),
    }
  );

  const summary = JSON.parse(stdout) as {
    annotationDirPath: string | null;
    failureSummary: {
      totals: { derivedAnnotationFailures: number };
      categoryCounts: Record<string, number>;
    };
    failureSummaryPath: string;
    textureQualityGatePath: string | null;
    textureQualityGate: {
      ok: boolean;
      rates: { directlyUsableRate: number | null; contaminationRate: number | null };
    } | null;
    nextSteps: string[];
  };
  assert.equal(summary.annotationDirPath, annotationDir);
  assert.equal(summary.failureSummary.totals.derivedAnnotationFailures, 3);
  assert.equal(summary.failureSummary.categoryCounts.postprocess, 3);
  assert.equal(summary.textureQualityGatePath, path.join(outputDir, "texture-quality-gate.json"));
  assert.equal(summary.textureQualityGate?.ok, false);
  assert.equal(summary.textureQualityGate?.rates.directlyUsableRate, 0);
  assert.equal(summary.textureQualityGate?.rates.contaminationRate, 0);
  assert.ok(summary.nextSteps.some((item) => item.includes("Texture quality gate still needs improvement")));

  const persisted = JSON.parse(await readFile(summary.failureSummaryPath, "utf8")) as {
    totals: { derivedAnnotationFailures: number };
    derivedAnnotationBreakdown: { subcategoryCounts: Record<string, number> };
  };
  assert.equal(persisted.totals.derivedAnnotationFailures, 3);
  assert.equal(
    persisted.derivedAnnotationBreakdown.subcategoryCounts["postprocess/highlight_hotspots"],
    2
  );
  assert.equal(
    persisted.derivedAnnotationBreakdown.subcategoryCounts["postprocess/mask_crop_touches_edge"],
    1
  );

  const persistedTextureGate = JSON.parse(
    await readFile(summary.textureQualityGatePath!, "utf8")
  ) as {
    ok: boolean;
    rates: { directlyUsableRate: number | null; contaminationRate: number | null };
  };
  assert.equal(persistedTextureGate.ok, false);
  assert.equal(persistedTextureGate.rates.directlyUsableRate, 0);
});
