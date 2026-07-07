import assert from "node:assert/strict";
import { execFile } from "node:child_process";
import { mkdtemp, mkdir, readFile, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { promisify } from "node:util";
import test from "node:test";

const execFileAsync = promisify(execFile);

async function createRelease(root: string, version: string, metrics: object, modelBytes: number) {
  const exportsDir = path.join(root, "model", "exports", version);
  const modelDir = path.join(root, "public", "models", `${version}-browser`);
  await mkdir(exportsDir, { recursive: true });
  await mkdir(modelDir, { recursive: true });

  const metricsPath = path.join(exportsDir, "metrics.json");
  const manifestPath = path.join(modelDir, "manifest.json");
  const modelFile = `${version}.onnx`;
  await writeFile(metricsPath, JSON.stringify(metrics, null, 2), "utf8");
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
  await writeFile(path.join(modelDir, modelFile), Buffer.alloc(modelBytes), "binary");
  return { metricsPath, manifestPath };
}

async function writeFailureSummary(
  root: string,
  version: string,
  values: {
    postprocess: number;
    highlightHotspots: number;
    derivedAnnotationFailures: number;
    inferredRecordFailure?: number;
    extraCategories?: Record<string, number>;
  }
) {
  const summaryPath = path.join(root, "model", "exports", version, "failure-case-summary.json");
  await writeFile(
    summaryPath,
    JSON.stringify(
      {
        totals: {
          derivedAnnotationFailures: values.derivedAnnotationFailures,
          inferredRecordFailure: values.inferredRecordFailure ?? 0,
          csvRows: 0,
        },
        categoryCounts: {
          postprocess: values.postprocess,
          ...(values.extraCategories ?? {}),
        },
        derivedAnnotationBreakdown: {
          subcategoryCounts: {
            "postprocess/highlight_hotspots": values.highlightHotspots,
          },
        },
      },
      null,
      2
    ),
    "utf8"
  );
  return summaryPath;
}

async function writeTraceIndex(
  root: string,
  version: string,
  values: {
    importedSampleCount: number;
    importedByPriority: Record<string, number>;
    warningBreakdown: Record<string, number>;
    backendBreakdown: Record<string, number>;
    readinessTotals: { images: number; validMasks: number };
  }
) {
  const traceIndexPath = path.join(root, "model", "exports", version, "release-trace-index.json");
  await writeFile(
    traceIndexPath,
    JSON.stringify(
      {
        candidateVersion: version,
        activeLearning: {
          importedSampleCount: values.importedSampleCount,
          importedByPriority: values.importedByPriority,
          prioritySummary: {
            warningBreakdown: values.warningBreakdown,
            backendBreakdown: values.backendBreakdown,
          },
          readinessSnapshot: {
            totals: values.readinessTotals,
          },
        },
      },
      null,
      2
    ),
    "utf8"
  );
  return traceIndexPath;
}

test("compare-training-releases reports improvement summary and can persist output", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-compare-release-pass-"));
  const baseline = await createRelease(
    root,
    "nail-texture-seg-v1",
    {
      split: "test",
      imgsz: 640,
      dry_run: false,
      box_map50: 0.86,
      box_map: 0.78,
      seg_map50: 0.76,
      seg_map: 0.68,
    },
    1024
  );
  const candidate = await createRelease(
    root,
    "nail-texture-seg-v2",
    {
      split: "test",
      imgsz: 640,
      dry_run: false,
      box_map50: 0.9,
      box_map: 0.82,
      seg_map50: 0.8,
      seg_map: 0.72,
    },
    2048
  );
  const outputPath = path.join(root, "compare-summary.json");

  const { stdout } = await execFileAsync(
    process.execPath,
    [
      "--no-warnings",
      "--experimental-strip-types",
      "scripts/compare-training-releases.ts",
      "--baseline-metrics",
      baseline.metricsPath,
      "--baseline-manifest",
      baseline.manifestPath,
      "--candidate-metrics",
      candidate.metricsPath,
      "--candidate-manifest",
      candidate.manifestPath,
      "--output",
      outputPath,
    ],
    { cwd: path.resolve(".") }
  );

  const summary = JSON.parse(stdout) as {
    ok: boolean;
    deltas: { seg_map50: number; box_map50: number };
    improvements: string[];
    warnings: string[];
  };
  assert.equal(summary.ok, true);
  assert.equal(summary.deltas.seg_map50, 0.04);
  assert.equal(summary.deltas.box_map50, 0.04);
  assert.ok(summary.improvements.some((item) => item.includes("seg_map50 improved")));
  assert.ok(summary.warnings.some((item) => item.includes("candidate model is larger")));

  const persisted = JSON.parse(await readFile(outputPath, "utf8")) as {
    ok: boolean;
    candidate: { version: string };
  };
  assert.equal(persisted.ok, true);
  assert.equal(persisted.candidate.version, "nail-texture-seg-v2");
});

test("compare-training-releases can compare active-learning trace indexes", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-compare-release-active-learning-"));
  const baseline = await createRelease(
    root,
    "nail-texture-seg-v1",
    {
      split: "test",
      imgsz: 640,
      dry_run: false,
      box_map50: 0.86,
      box_map: 0.78,
      seg_map50: 0.76,
      seg_map: 0.68,
    },
    1024
  );
  const candidate = await createRelease(
    root,
    "nail-texture-seg-v2",
    {
      split: "test",
      imgsz: 640,
      dry_run: false,
      box_map50: 0.87,
      box_map: 0.79,
      seg_map50: 0.77,
      seg_map: 0.69,
    },
    1024
  );
  const baselineTraceIndex = await writeTraceIndex(root, "nail-texture-seg-v1", {
    importedSampleCount: 2,
    importedByPriority: { high: 1, medium: 1 },
    warningBreakdown: { onnx_runtime_not_loaded: 2 },
    backendBreakdown: { fallback: 2 },
    readinessTotals: { images: 20, validMasks: 70 },
  });
  const candidateTraceIndex = await writeTraceIndex(root, "nail-texture-seg-v2", {
    importedSampleCount: 5,
    importedByPriority: { high: 3, medium: 2 },
    warningBreakdown: { onnx_runtime_not_loaded: 1, model_inference_error: 2 },
    backendBreakdown: { fallback: 1, model: 4 },
    readinessTotals: { images: 28, validMasks: 96 },
  });

  const { stdout } = await execFileAsync(
    process.execPath,
    [
      "--no-warnings",
      "--experimental-strip-types",
      "scripts/compare-training-releases.ts",
      "--baseline-metrics",
      baseline.metricsPath,
      "--baseline-manifest",
      baseline.manifestPath,
      "--candidate-metrics",
      candidate.metricsPath,
      "--candidate-manifest",
      candidate.manifestPath,
      "--baseline-trace-index",
      baselineTraceIndex,
      "--candidate-trace-index",
      candidateTraceIndex,
    ],
    { cwd: path.resolve(".") }
  );

  const summary = JSON.parse(stdout) as {
    baseline: { activeLearning: { importedSampleCount: number } | null };
    candidate: {
      traceIndexPath: string | null;
      activeLearning: {
        importedSampleCount: number;
        readinessTotals: { images: number; validMasks: number } | null;
      } | null;
    };
    deltas: {
      activeLearningImportedSamples: number | null;
      activeLearningWarnings: Record<string, number> | null;
      activeLearningBackends: Record<string, number> | null;
    };
    improvements: string[];
    warnings: string[];
  };

  assert.equal(summary.baseline.activeLearning?.importedSampleCount, 2);
  assert.equal(summary.candidate.traceIndexPath, candidateTraceIndex);
  assert.equal(summary.candidate.activeLearning?.importedSampleCount, 5);
  assert.deepEqual(summary.candidate.activeLearning?.readinessTotals, {
    images: 28,
    validMasks: 96,
  });
  assert.equal(summary.deltas.activeLearningImportedSamples, 3);
  assert.deepEqual(summary.deltas.activeLearningWarnings, {
    model_inference_error: 2,
    onnx_runtime_not_loaded: -1,
  });
  assert.deepEqual(summary.deltas.activeLearningBackends, {
    fallback: -1,
    model: 4,
  });
  assert.ok(
    summary.improvements.some((item) =>
      item.includes("active-learning imported sample count increased by 3")
    )
  );
  assert.ok(
    summary.warnings.some((item) =>
      item.includes("candidate active-learning warning count increased by 1")
    )
  );
});

test("compare-training-releases fails when candidate regresses too much", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-compare-release-fail-"));
  const baseline = await createRelease(
    root,
    "nail-texture-seg-v1",
    {
      split: "test",
      imgsz: 640,
      dry_run: false,
      box_map50: 0.9,
      box_map: 0.82,
      seg_map50: 0.82,
      seg_map: 0.74,
    },
    1024
  );
  const candidate = await createRelease(
    root,
    "nail-texture-seg-v2",
    {
      split: "test",
      imgsz: 640,
      dry_run: false,
      box_map50: 0.84,
      box_map: 0.76,
      seg_map50: 0.75,
      seg_map: 0.67,
    },
    1024
  );

  await assert.rejects(
    execFileAsync(
      process.execPath,
      [
        "--no-warnings",
        "--experimental-strip-types",
        "scripts/compare-training-releases.ts",
        "--baseline-metrics",
        baseline.metricsPath,
        "--baseline-manifest",
        baseline.manifestPath,
        "--candidate-metrics",
        candidate.metricsPath,
        "--candidate-manifest",
        candidate.manifestPath,
      ],
      { cwd: path.resolve(".") }
    ),
    (error: Error & { stdout?: string }) => {
      const summary = JSON.parse(error.stdout ?? "{}") as {
        ok: boolean;
        regressions: string[];
      };
      assert.equal(summary.ok, false);
      assert.ok(summary.regressions.some((item) => item.includes("seg_map50 regressed")));
      assert.ok(summary.regressions.some((item) => item.includes("box_map50 regressed")));
      return true;
    }
  );
});

test("compare-training-releases can compare failure summaries between releases", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-compare-release-failure-summary-"));
  const baseline = await createRelease(
    root,
    "nail-texture-seg-v1",
    {
      split: "test",
      imgsz: 640,
      dry_run: false,
      box_map50: 0.86,
      box_map: 0.78,
      seg_map50: 0.76,
      seg_map: 0.68,
    },
    1024
  );
  const candidate = await createRelease(
    root,
    "nail-texture-seg-v2",
    {
      split: "test",
      imgsz: 640,
      dry_run: false,
      box_map50: 0.87,
      box_map: 0.79,
      seg_map50: 0.77,
      seg_map: 0.69,
    },
    1024
  );
  const baselineFailureSummary = await writeFailureSummary(root, "nail-texture-seg-v1", {
    postprocess: 5,
    highlightHotspots: 3,
    derivedAnnotationFailures: 5,
  });
  const candidateFailureSummary = await writeFailureSummary(root, "nail-texture-seg-v2", {
    postprocess: 2,
    highlightHotspots: 1,
    derivedAnnotationFailures: 2,
  });

  const { stdout } = await execFileAsync(
    process.execPath,
    [
      "--no-warnings",
      "--experimental-strip-types",
      "scripts/compare-training-releases.ts",
      "--baseline-metrics",
      baseline.metricsPath,
      "--baseline-manifest",
      baseline.manifestPath,
      "--candidate-metrics",
      candidate.metricsPath,
      "--candidate-manifest",
      candidate.manifestPath,
      "--baseline-failure-summary",
      baselineFailureSummary,
      "--candidate-failure-summary",
      candidateFailureSummary,
    ],
    { cwd: path.resolve(".") }
  );

  const summary = JSON.parse(stdout) as {
    deltas: {
      failureCategories: Record<string, number> | null;
      failureTotal: number | null;
      derivedAnnotationFailures: number | null;
      inferredRecordFailures: number | null;
      postprocessFailures: number;
      highlightHotspotFailures: number;
    };
    improvements: string[];
    baseline: { failureSummaryPath: string | null };
    candidate: { failureSummary: { totals: { derivedAnnotationFailures: number } } | null };
  };
  assert.deepEqual(summary.deltas.failureCategories, { postprocess: -3 });
  assert.equal(summary.deltas.failureTotal, -3);
  assert.equal(summary.deltas.derivedAnnotationFailures, -3);
  assert.equal(summary.deltas.inferredRecordFailures, 0);
  assert.equal(summary.deltas.postprocessFailures, -3);
  assert.equal(summary.deltas.highlightHotspotFailures, -2);
  assert.equal(summary.baseline.failureSummaryPath, baselineFailureSummary);
  assert.equal(summary.candidate.failureSummary?.totals.derivedAnnotationFailures, 2);
  assert.ok(summary.improvements.some((item) => item.includes("postprocess failure count decreased")));
  assert.ok(summary.improvements.some((item) => item.includes("highlight hotspot failures decreased")));
});

test("compare-training-releases reports full failure taxonomy deltas", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-compare-release-failure-taxonomy-"));
  const baseline = await createRelease(
    root,
    "nail-texture-seg-v1",
    {
      split: "test",
      imgsz: 640,
      dry_run: false,
      box_map50: 0.86,
      box_map: 0.78,
      seg_map50: 0.76,
      seg_map: 0.68,
    },
    1024
  );
  const candidate = await createRelease(
    root,
    "nail-texture-seg-v2",
    {
      split: "test",
      imgsz: 640,
      dry_run: false,
      box_map50: 0.87,
      box_map: 0.79,
      seg_map50: 0.77,
      seg_map: 0.69,
    },
    1024
  );
  const baselineFailureSummary = await writeFailureSummary(root, "nail-texture-seg-v1", {
    postprocess: 1,
    highlightHotspots: 0,
    derivedAnnotationFailures: 1,
    inferredRecordFailure: 0,
    extraCategories: { data: 1 },
  });
  const candidateFailureSummary = await writeFailureSummary(root, "nail-texture-seg-v2", {
    postprocess: 2,
    highlightHotspots: 1,
    derivedAnnotationFailures: 4,
    inferredRecordFailure: 2,
    extraCategories: { data: 0, ui: 3 },
  });

  const { stdout } = await execFileAsync(
    process.execPath,
    [
      "--no-warnings",
      "--experimental-strip-types",
      "scripts/compare-training-releases.ts",
      "--baseline-metrics",
      baseline.metricsPath,
      "--baseline-manifest",
      baseline.manifestPath,
      "--candidate-metrics",
      candidate.metricsPath,
      "--candidate-manifest",
      candidate.manifestPath,
      "--baseline-failure-summary",
      baselineFailureSummary,
      "--candidate-failure-summary",
      candidateFailureSummary,
    ],
    { cwd: path.resolve(".") }
  );

  const summary = JSON.parse(stdout) as {
    deltas: {
      failureCategories: Record<string, number> | null;
      failureTotal: number | null;
      derivedAnnotationFailures: number | null;
      inferredRecordFailures: number | null;
    };
    warnings: string[];
    improvements: string[];
  };

  assert.deepEqual(summary.deltas.failureCategories, {
    data: -1,
    postprocess: 1,
    ui: 3,
  });
  assert.equal(summary.deltas.failureTotal, 3);
  assert.equal(summary.deltas.derivedAnnotationFailures, 3);
  assert.equal(summary.deltas.inferredRecordFailures, 2);
  assert.ok(
    summary.warnings.some((item) =>
      item.includes("candidate failure categories increased (postprocess+1, ui+3)")
    )
  );
  assert.ok(
    summary.warnings.some((item) =>
      item.includes("candidate total classified failures increased by 3")
    )
  );
  assert.ok(
    summary.improvements.some((item) => item.includes("failure categories decreased (data-1)"))
  );
});
