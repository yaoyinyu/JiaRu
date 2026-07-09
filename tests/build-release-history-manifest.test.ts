import assert from "node:assert/strict";
import { execFile } from "node:child_process";
import { mkdtemp, mkdir, readFile, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { promisify } from "node:util";
import test from "node:test";

const execFileAsync = promisify(execFile);

test("build-release-history-manifest summarizes multiple release trace indexes", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-release-history-"));
  const reportDir = path.join(root, "reports");
  await mkdir(reportDir, { recursive: true });

  const traceA = path.join(reportDir, "trace-a.json");
  const traceB = path.join(reportDir, "trace-b.json");

  await writeFile(
    traceA,
    JSON.stringify(
      {
        candidateVersion: "nail-texture-seg-v1",
        currentRegistryVersion: "nail-texture-seg-v2",
        batch: {
          sourceGroup: "seed-batch-001",
          datasetRoot: "C:/tmp/dataset",
          importedFileCount: 2,
        },
        activeLearning: {
          importedSampleCount: 4,
          importedByPriority: { high: 2, medium: 2 },
          prioritySummary: {
            backendBreakdown: { fallback: 3, model: 1 },
            warningBreakdown: { onnx_runtime_not_loaded: 2 },
          },
          readinessSnapshot: {
            totals: { images: 20, validMasks: 70 },
          },
        },
        release: {
          trainingReleasePipelineReportPath: "C:/tmp/v1/training-release-pipeline-report.json",
          firstRunOutputs: {
            debugJsonPath: "C:/tmp/v1/real-model-5188-detection-debug.json",
            recognitionMaskPath: "C:/tmp/v1/real-model-5188-recognition-mask-overlay.png",
          },
          finalAuditStatus: "pass",
          derivedAnnotationFailures: 1,
          postprocessFailures: 1,
          failureCategoryCounts: { postprocess: 1, inferred_record: 2 },
          failureSummaryTotals: {
            csvRows: 3,
            derivedAnnotationFailures: 1,
            inferredRecordFailures: 2,
          },
        },
        decision: {
          status: "manual_review",
          summary: "review needed",
        },
        promotion: {
          registeredVersion: "nail-texture-seg-v1",
          currentVersion: "nail-texture-seg-v2",
        },
        links: {
          sourceGroupToCandidateVersion: "seed-batch-001 -> nail-texture-seg-v1",
        },
      },
      null,
      2
    ),
    "utf8"
  );

  await writeFile(
    traceB,
    JSON.stringify(
      {
        candidateVersion: "nail-texture-seg-v2",
        currentRegistryVersion: "nail-texture-seg-v2",
        batch: {
          sourceGroup: "seed-batch-002",
          datasetRoot: "C:/tmp/dataset",
          importedFileCount: 3,
        },
        activeLearning: {
          importedSampleCount: 1,
          importedByPriority: { high: 1 },
          prioritySummary: {
            backendBreakdown: { model: 1 },
            warningBreakdown: { model_inference_error: 1, onnx_runtime_not_loaded: 1 },
          },
          readinessSnapshot: {
            totals: { images: 25, validMasks: 90 },
          },
        },
        release: {
          trainingReleasePipelineReportPath: "C:/tmp/v2/training-release-pipeline-report.json",
          firstRunOutputs: {
            debugJsonPath: "C:/tmp/v2/real-model-5188-detection-debug.json",
            recognitionMaskPath: null,
          },
          finalAuditStatus: "pass",
          derivedAnnotationFailures: 0,
          postprocessFailures: 0,
          failureCategoryCounts: { low_confidence: 1 },
          failureSummaryTotals: {
            csvRows: 1,
            derivedAnnotationFailures: 0,
            inferredRecordFailures: 0,
          },
        },
        decision: {
          status: "approve_candidate",
          summary: "ok",
        },
        promotion: {
          registeredVersion: "nail-texture-seg-v2",
          currentVersion: "nail-texture-seg-v2",
        },
        links: {
          sourceGroupToCandidateVersion: "seed-batch-002 -> nail-texture-seg-v2",
        },
      },
      null,
      2
    ),
    "utf8"
  );

  const { stdout } = await execFileAsync(
    process.execPath,
    [
      "--no-warnings",
      "--experimental-strip-types",
      "scripts/build-release-history-manifest.ts",
      "--trace-index",
      traceA,
      "--trace-index",
      traceB,
    ],
    { cwd: path.resolve(".") }
  );

  const summary = JSON.parse(stdout) as {
    totals: {
      traceIndexes: number;
      uniqueCandidateVersions: number;
      uniqueSourceGroups: number;
      activeLearningTraceIndexes: number;
      activeLearningImportedSamples: number;
      failureTraceIndexes: number;
      failureCategoryTotal: number;
      failureSummaryCsvRows: number;
      failureSummaryInferredRecordFailures: number;
    };
    decisionCounts: Record<string, number>;
    finalAuditStatusCounts: Record<string, number>;
    activeLearning: {
      importedByPriority: Record<string, number>;
      warningBreakdown: Record<string, number>;
      backendBreakdown: Record<string, number>;
    };
    failureSummary: {
      categoryBreakdown: Record<string, number>;
      categoryTotal: number;
      csvRows: number;
      inferredRecordFailures: number;
      derivedAnnotationFailures: number;
      postprocessFailures: number;
    };
    sourceGroups: string[];
    registeredVersions: string[];
    entries: Array<{
      candidateVersion: string | null;
      sourceGroup: string | null;
      activeLearningImportedSampleCount: number;
      activeLearningWarningBreakdown: Record<string, number> | null;
      activeLearningReadinessTotals: { images: number; validMasks: number } | null;
      failureCategoryCounts: Record<string, number> | null;
      failureSummaryTotals: {
        csvRows?: number;
        derivedAnnotationFailures?: number;
        inferredRecordFailures?: number;
      } | null;
    }>;
    outputPath: string;
  };

  assert.equal(summary.totals.traceIndexes, 2);
  assert.equal(summary.totals.uniqueCandidateVersions, 2);
  assert.equal(summary.totals.uniqueSourceGroups, 2);
  assert.equal(summary.totals.activeLearningTraceIndexes, 2);
  assert.equal(summary.totals.activeLearningImportedSamples, 5);
  assert.equal(summary.totals.failureTraceIndexes, 2);
  assert.equal(summary.totals.failureCategoryTotal, 4);
  assert.equal(summary.totals.failureSummaryCsvRows, 4);
  assert.equal(summary.totals.failureSummaryInferredRecordFailures, 2);
  assert.equal(summary.totals.visualEvidenceTraceIndexes, 2);
  assert.equal(summary.totals.recognitionMaskEvidenceTraceIndexes, 1);
  assert.equal(summary.decisionCounts.approve_candidate, 1);
  assert.equal(summary.decisionCounts.manual_review, 1);
  assert.equal(summary.finalAuditStatusCounts.pass, 2);
  assert.deepEqual(summary.activeLearning.importedByPriority, { high: 3, medium: 2 });
  assert.deepEqual(summary.activeLearning.warningBreakdown, {
    onnx_runtime_not_loaded: 3,
    model_inference_error: 1,
  });
  assert.deepEqual(summary.activeLearning.backendBreakdown, { fallback: 3, model: 2 });
  assert.deepEqual(summary.failureSummary.categoryBreakdown, {
    postprocess: 1,
    inferred_record: 2,
    low_confidence: 1,
  });
  assert.equal(summary.failureSummary.categoryTotal, 4);
  assert.equal(summary.failureSummary.csvRows, 4);
  assert.equal(summary.failureSummary.inferredRecordFailures, 2);
  assert.equal(summary.failureSummary.derivedAnnotationFailures, 1);
  assert.equal(summary.failureSummary.postprocessFailures, 1);
  assert.deepEqual(summary.sourceGroups, ["seed-batch-001", "seed-batch-002"]);
  assert.deepEqual(summary.registeredVersions, ["nail-texture-seg-v1", "nail-texture-seg-v2"]);
  assert.deepEqual(
    summary.entries.map((entry) => entry.candidateVersion),
    ["nail-texture-seg-v1", "nail-texture-seg-v2"]
  );
  assert.equal(summary.entries[0]?.activeLearningImportedSampleCount, 4);
  assert.deepEqual(summary.entries[1]?.activeLearningWarningBreakdown, {
    model_inference_error: 1,
    onnx_runtime_not_loaded: 1,
  });
  assert.deepEqual(summary.entries[1]?.activeLearningReadinessTotals, {
    images: 25,
    validMasks: 90,
  });
  assert.deepEqual(summary.entries[0]?.failureCategoryCounts, {
    postprocess: 1,
    inferred_record: 2,
  });
  assert.deepEqual(summary.entries[1]?.failureSummaryTotals, {
    csvRows: 1,
    derivedAnnotationFailures: 0,
    inferredRecordFailures: 0,
  });

  const saved = JSON.parse(await readFile(summary.outputPath, "utf8")) as {
    totals: { traceIndexes: number; activeLearningImportedSamples: number; failureCategoryTotal: number };
  };
  assert.equal(saved.totals.traceIndexes, 2);
  assert.equal(saved.totals.activeLearningImportedSamples, 5);
  assert.equal(saved.totals.failureCategoryTotal, 4);
});
