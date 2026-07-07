import assert from "node:assert/strict";
import { execFile } from "node:child_process";
import { mkdtemp, mkdir, readFile, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { promisify } from "node:util";
import test from "node:test";

const execFileAsync = promisify(execFile);

async function createManifest(modelDir: string, version: string, sizeBytes = 1024) {
  const manifestPath = path.join(modelDir, "manifest.json");
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
  await writeFile(path.join(modelDir, modelFile), Buffer.alloc(sizeBytes), "binary");
  return manifestPath;
}

async function registerRelease(manifestPath: string, registryPath: string) {
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
}
test("run-release-governance-pipeline can build decision promote trace and history in one pass", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-release-governance-pass-"));
  const reportsDir = path.join(root, "reports");
  const modelDir = path.join(root, "public", "models", "nail-texture-seg");
  await mkdir(reportsDir, { recursive: true });
  await mkdir(modelDir, { recursive: true });

  const manifestPath = await createManifest(modelDir, "nail-texture-seg-v2");
  const trainingReleasePipelineReportPath = path.join(
    reportsDir,
    "training-release-pipeline-report.json"
  );
  await writeFile(
    trainingReleasePipelineReportPath,
    JSON.stringify(
      {
        ok: true,
        reportPath: trainingReleasePipelineReportPath,
        paths: {
          manifestPath,
          metricsPath: path.join(reportsDir, "metrics.json"),
          trainOutputDir: path.join(root, "model", "exports", "nail-texture-seg-v2"),
        },
        artifacts: {
          manifest: { version: "nail-texture-seg-v2", modelFile: "nail-texture-seg-v2.onnx" },
          metrics: { seg_map50: 0.81, box_map50: 0.9 },
          finalAudit: {
            ok: true,
            decision: { status: "pass", summary: "audit ok", nextActions: [] },
          },
          finalAuditFailureSummary: {
            totals: { derivedAnnotationFailures: 0, inferredRecordFailure: 0, csvRows: 0 },
            categoryCounts: {},
          },
          finalAuditTextureQualityGate: {
            ok: true,
            directlyUsableCount: 17,
            directlyUsableRate: 0.85,
            contaminatedCount: 1,
            contaminationRate: 0.05,
            evidence: {
              ok: true,
              scope: "release-test-split",
              representativeTestSplit: true,
              documentsOk: true,
              candidatesWithDebugOk: true,
              candidatesWithPolygonOk: true,
              minDocuments: 20,
              minCandidatesWithDebug: 100,
              minCandidatesWithPolygon: 100,
            },
            warningBreakdown: {},
            warnings: [],
            nextSteps: [],
          },
        },
        steps: [
          {
            name: "run-real-model-final-audit",
            stdout: {
              finalReportPath: path.join(reportsDir, "real-model-final-audit-report.json"),
              failureSummaryPath: path.join(reportsDir, "failure-case-summary.json"),
              recordPath: path.join(reportsDir, "real-model-first-run-record.json"),
            },
          },
        ],
      },
      null,
      2
    ),
    "utf8"
  );

  const compareSummaryPath = path.join(reportsDir, "compare-summary.json");
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

  const releaseTraceDraftPath = path.join(reportsDir, "release-trace-draft.json");
  await writeFile(
    releaseTraceDraftPath,
    JSON.stringify(
      {
        draft: true,
        batch: {
          rootDir: "C:/tmp/seed-batch-010",
          sourceGroup: "seed-batch-010",
          datasetRoot: "C:/tmp/dataset",
          reviewedImportReportPath: "C:/tmp/dataset/metadata/reviewed-import-seed-batch-010.report.json",
          importedFileCount: 5,
        },
      },
      null,
      2
    ),
    "utf8"
  );

  const registryPath = path.join(modelDir, "release-registry.json");
  await registerRelease(await createManifest(modelDir, "nail-texture-seg-v1"), registryPath);
  await createManifest(modelDir, "nail-texture-seg-v2");

  const historyManifestPath = path.join(reportsDir, "release-history-manifest.json");
  const { stdout } = await execFileAsync(
    process.execPath,
    [
      "--no-warnings",
      "--experimental-strip-types",
      "scripts/run-release-governance-pipeline.ts",
      "--training-release-pipeline-report",
      trainingReleasePipelineReportPath,
      "--compare-summary",
      compareSummaryPath,
      "--registry",
      registryPath,
      "--release-trace-draft",
      releaseTraceDraftPath,
      "--history-manifest",
      historyManifestPath,
    ],
    { cwd: path.resolve(".") }
  );

  const report = JSON.parse(stdout) as {
    ok: boolean;
    steps: Array<{ name: string; ok: boolean }>;
    artifacts: {
      releaseDecision: {
        decision: { status: string };
        inputs: {
          textureQualityGateOk: boolean | null;
          phase2ExtractionEvidenceOk: boolean | null;
          phase2ExtractionEvidenceScope: string | null;
          directlyUsableRate: number | null;
        };
      };
      promotion: { registerSummary: { registeredVersion: string } };
      traceIndex: { links: { sourceGroupToCandidateVersion: string | null } };
      rollbackAudit: { ok: boolean; rollbackCandidateCount: number; rollbackCandidates: string[] } | null;
      historyManifest: { totals: { traceIndexes: number } };
    };
  };
  assert.equal(report.ok, true);
  assert.deepEqual(report.steps.map((step) => step.name), [
    "build-release-decision-report",
    "promote-approved-release",
    "build-release-trace-index",
    "register-release-trace-index",
    "audit-release-rollback",
  ]);
  assert.equal(report.artifacts.releaseDecision.decision.status, "approve_candidate");
  assert.equal(report.artifacts.releaseDecision.inputs.textureQualityGateOk, true);
  assert.equal(report.artifacts.releaseDecision.inputs.phase2ExtractionEvidenceOk, true);
  assert.equal(report.artifacts.releaseDecision.inputs.phase2ExtractionEvidenceScope, "release-test-split");
  assert.equal(report.artifacts.releaseDecision.inputs.directlyUsableRate, 0.85);
  assert.equal(report.artifacts.promotion.registerSummary.registeredVersion, "nail-texture-seg-v2");
  assert.equal(
    report.artifacts.traceIndex.links.sourceGroupToCandidateVersion,
    "seed-batch-010 -> nail-texture-seg-v2"
  );
  assert.equal(report.artifacts.rollbackAudit?.ok, true);
  assert.equal(report.artifacts.rollbackAudit?.rollbackCandidateCount, 1);
  assert.deepEqual(report.artifacts.rollbackAudit?.rollbackCandidates, ["nail-texture-seg-v1"]);
  assert.equal(report.artifacts.historyManifest.totals.traceIndexes, 1);

  const savedHistory = JSON.parse(await readFile(historyManifestPath, "utf8")) as {
    entries: Array<{ candidateVersion: string | null }>;
  };
  assert.equal(savedHistory.entries[0]?.candidateVersion, "nail-texture-seg-v2");
});

test("run-release-governance-pipeline still builds decision and trace when candidate is held", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-release-governance-hold-"));
  const reportsDir = path.join(root, "reports");
  const modelDir = path.join(root, "public", "models", "nail-texture-seg");
  await mkdir(reportsDir, { recursive: true });
  await mkdir(modelDir, { recursive: true });

  const manifestPath = await createManifest(modelDir, "nail-texture-seg-v2");
  const trainingReleasePipelineReportPath = path.join(
    reportsDir,
    "training-release-pipeline-report.json"
  );
  await writeFile(
    trainingReleasePipelineReportPath,
    JSON.stringify(
      {
        ok: false,
        reportPath: trainingReleasePipelineReportPath,
        paths: {
          manifestPath,
          metricsPath: path.join(reportsDir, "metrics.json"),
          trainOutputDir: path.join(root, "model", "exports", "nail-texture-seg-v2"),
        },
        artifacts: {
          manifest: { version: "nail-texture-seg-v2", modelFile: "nail-texture-seg-v2.onnx" },
          finalAudit: {
            ok: false,
            decision: { status: "blocked", summary: "artifact missing", nextActions: ["fix model"] },
          },
          finalAuditFailureSummary: {
            totals: { derivedAnnotationFailures: 2, inferredRecordFailure: 0, csvRows: 0 },
            categoryCounts: { postprocess: 2 },
          },
        },
        steps: [],
      },
      null,
      2
    ),
    "utf8"
  );

  const releaseTraceDraftPath = path.join(reportsDir, "release-trace-draft.json");
  await writeFile(
    releaseTraceDraftPath,
    JSON.stringify(
      {
        draft: true,
        batch: {
          rootDir: "C:/tmp/seed-batch-011",
          sourceGroup: "seed-batch-011",
          datasetRoot: "C:/tmp/dataset",
          reviewedImportReportPath: "C:/tmp/dataset/metadata/reviewed-import-seed-batch-011.report.json",
          importedFileCount: 3,
        },
      },
      null,
      2
    ),
    "utf8"
  );

  try {
    await execFileAsync(
      process.execPath,
      [
        "--no-warnings",
        "--experimental-strip-types",
        "scripts/run-release-governance-pipeline.ts",
        "--training-release-pipeline-report",
        trainingReleasePipelineReportPath,
        "--release-trace-draft",
        releaseTraceDraftPath,
      ],
      { cwd: path.resolve(".") }
    );
    assert.fail("expected run-release-governance-pipeline to exit non-zero when decision is hold");
  } catch (error) {
    const execError = error as Error & { stdout?: string };
    const report = JSON.parse(execError.stdout ?? "{}") as {
      ok: boolean;
      steps: Array<{ name: string; ok: boolean; stdout?: { skipped?: boolean } }>;
      artifacts: {
        releaseDecision: { decision: { status: string } };
        promotion: unknown | null;
        traceIndex: { batch: { sourceGroup: string | null } | null };
        rollbackAudit: { skipped?: boolean } | null;
      };
    };
    assert.equal(report.ok, false);
    assert.equal(report.artifacts.releaseDecision.decision.status, "hold_candidate");
    assert.equal(report.steps[1]?.name, "promote-approved-release");
    assert.equal(report.steps[1]?.stdout?.skipped, true);
    assert.equal(report.artifacts.traceIndex.batch?.sourceGroup, "seed-batch-011");
    assert.equal(report.steps[3]?.name, "register-release-trace-index");
    assert.equal(report.steps[3]?.stdout?.skipped, true);
    assert.equal(report.steps[4]?.name, "audit-release-rollback");
    assert.equal(report.steps[4]?.stdout?.skipped, true);
  }
});

test("run-release-governance-pipeline keeps active-learning warning reviews out of automatic promotion", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-release-governance-active-learning-review-"));
  const reportsDir = path.join(root, "reports");
  const modelDir = path.join(root, "public", "models", "nail-texture-seg");
  await mkdir(reportsDir, { recursive: true });
  await mkdir(modelDir, { recursive: true });

  const manifestPath = await createManifest(modelDir, "nail-texture-seg-v4");
  const trainingReleasePipelineReportPath = path.join(
    reportsDir,
    "training-release-pipeline-report.json"
  );
  await writeFile(
    trainingReleasePipelineReportPath,
    JSON.stringify(
      {
        ok: true,
        reportPath: trainingReleasePipelineReportPath,
        paths: {
          manifestPath,
          metricsPath: path.join(reportsDir, "metrics.json"),
          trainOutputDir: path.join(root, "model", "exports", "nail-texture-seg-v4"),
        },
        artifacts: {
          manifest: { version: "nail-texture-seg-v4", modelFile: "nail-texture-seg-v4.onnx" },
          metrics: { seg_map50: 0.83, box_map50: 0.92 },
          finalAudit: {
            ok: true,
            decision: { status: "pass", summary: "audit ok", nextActions: [] },
          },
          finalAuditFailureSummary: {
            totals: { derivedAnnotationFailures: 0, inferredRecordFailure: 0, csvRows: 0 },
            categoryCounts: {},
          },
          finalAuditTextureQualityGate: {
            ok: true,
            rates: { directlyUsableRate: 0.9, contaminationRate: 0.03, roughRectangleRate: 0.05 },
            evidence: {
              ok: true,
              scope: "release-test-split",
              representativeTestSplit: true,
              documentsOk: true,
              candidatesWithDebugOk: true,
              candidatesWithPolygonOk: true,
            },
          },
        },
        steps: [],
      },
      null,
      2
    ),
    "utf8"
  );

  const compareSummaryPath = path.join(reportsDir, "compare-summary.json");
  await writeFile(
    compareSummaryPath,
    JSON.stringify(
      {
        ok: true,
        regressions: [],
        improvements: ["active-learning imported sample count increased by 3"],
        warnings: ["candidate active-learning warning count increased by 2"],
        deltas: {
          activeLearningImportedSamples: 3,
          activeLearningWarnings: {
            model_inference_error: 2,
            onnx_runtime_not_loaded: -1,
          },
          activeLearningBackends: {
            model: 4,
            fallback: -1,
          },
        },
      },
      null,
      2
    ),
    "utf8"
  );

  await assert.rejects(
    execFileAsync(
      process.execPath,
      [
        "--no-warnings",
        "--experimental-strip-types",
        "scripts/run-release-governance-pipeline.ts",
        "--training-release-pipeline-report",
        trainingReleasePipelineReportPath,
        "--compare-summary",
        compareSummaryPath,
      ],
      { cwd: path.resolve(".") }
    ),
    (error: unknown) => {
      const execError = error as Error & { stdout?: string };
      const report = JSON.parse(execError.stdout ?? "{}") as {
        ok: boolean;
        steps: Array<{ name: string; ok: boolean; stdout?: { skipped?: boolean; reason?: string } }>;
        artifacts: {
          releaseDecision: {
            decision: { status: string; reasons: string[]; nextActions: string[] };
            inputs: {
              activeLearningImportedSampleDelta: number | null;
              activeLearningWarningDelta: number;
              activeLearningWarningDeltas: Record<string, number> | null;
            };
          };
          promotion: { skipped?: boolean; reason?: string } | null;
          traceIndex: { decision: { status: string } | null };
          traceRegistration: { skipped?: boolean } | null;
          rollbackAudit: { skipped?: boolean } | null;
        };
      };
      assert.equal(report.ok, false);
      assert.equal(report.artifacts.releaseDecision.decision.status, "manual_review");
      assert.equal(report.artifacts.releaseDecision.inputs.activeLearningImportedSampleDelta, 3);
      assert.equal(report.artifacts.releaseDecision.inputs.activeLearningWarningDelta, 2);
      assert.deepEqual(report.artifacts.releaseDecision.inputs.activeLearningWarningDeltas, {
        model_inference_error: 2,
        onnx_runtime_not_loaded: -1,
      });
      assert.ok(
        report.artifacts.releaseDecision.decision.reasons.some((item) =>
          item.includes("active-learning warning signals increased by 2")
        )
      );
      assert.equal(report.steps.find((step) => step.name === "promote-approved-release")?.stdout?.skipped, true);
      assert.equal(report.artifacts.promotion?.skipped, true);
      assert.ok(report.artifacts.promotion?.reason?.includes("release decision did not allow automatic promotion"));
      assert.equal(report.artifacts.traceIndex.decision?.status, "manual_review");
      assert.equal(report.artifacts.traceRegistration?.skipped, true);
      assert.equal(report.artifacts.rollbackAudit?.skipped, true);
      return true;
    }
  );
});

test("run-release-governance-pipeline can promote active-learning warning reviews when explicitly allowed", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-release-governance-active-learning-allowed-"));
  const reportsDir = path.join(root, "reports");
  const modelDir = path.join(root, "public", "models", "nail-texture-seg");
  await mkdir(reportsDir, { recursive: true });
  await mkdir(modelDir, { recursive: true });

  const manifestPath = await createManifest(modelDir, "nail-texture-seg-v4");
  const trainingReleasePipelineReportPath = path.join(
    reportsDir,
    "training-release-pipeline-report.json"
  );
  await writeFile(
    trainingReleasePipelineReportPath,
    JSON.stringify(
      {
        ok: true,
        reportPath: trainingReleasePipelineReportPath,
        paths: {
          manifestPath,
          metricsPath: path.join(reportsDir, "metrics.json"),
          trainOutputDir: path.join(root, "model", "exports", "nail-texture-seg-v4"),
        },
        artifacts: {
          manifest: { version: "nail-texture-seg-v4", modelFile: "nail-texture-seg-v4.onnx" },
          metrics: { seg_map50: 0.83, box_map50: 0.92 },
          finalAudit: {
            ok: true,
            decision: { status: "pass", summary: "audit ok", nextActions: [] },
          },
          finalAuditFailureSummary: {
            totals: { derivedAnnotationFailures: 0, inferredRecordFailure: 0, csvRows: 0 },
            categoryCounts: {},
          },
          finalAuditTextureQualityGate: {
            ok: true,
            rates: { directlyUsableRate: 0.9, contaminationRate: 0.03, roughRectangleRate: 0.05 },
            evidence: {
              ok: true,
              scope: "release-test-split",
              representativeTestSplit: true,
              documentsOk: true,
              candidatesWithDebugOk: true,
              candidatesWithPolygonOk: true,
            },
          },
        },
        steps: [],
      },
      null,
      2
    ),
    "utf8"
  );

  const compareSummaryPath = path.join(reportsDir, "compare-summary.json");
  await writeFile(
    compareSummaryPath,
    JSON.stringify(
      {
        ok: true,
        regressions: [],
        improvements: ["active-learning imported sample count increased by 3"],
        warnings: ["candidate active-learning warning count increased by 2"],
        deltas: {
          activeLearningImportedSamples: 3,
          activeLearningWarnings: {
            model_inference_error: 2,
            onnx_runtime_not_loaded: -1,
          },
          activeLearningBackends: {
            model: 4,
            fallback: -1,
          },
        },
      },
      null,
      2
    ),
    "utf8"
  );

  const registryPath = path.join(modelDir, "release-registry.json");
  await registerRelease(await createManifest(modelDir, "nail-texture-seg-v3"), registryPath);
  await createManifest(modelDir, "nail-texture-seg-v4");
  const historyManifestPath = path.join(reportsDir, "release-history-manifest.json");

  const { stdout } = await execFileAsync(
    process.execPath,
    [
      "--no-warnings",
      "--experimental-strip-types",
      "scripts/run-release-governance-pipeline.ts",
      "--training-release-pipeline-report",
      trainingReleasePipelineReportPath,
      "--compare-summary",
      compareSummaryPath,
      "--registry",
      registryPath,
      "--history-manifest",
      historyManifestPath,
      "--allow-manual-review",
      "true",
    ],
    { cwd: path.resolve(".") }
  );

  const report = JSON.parse(stdout) as {
    ok: boolean;
    steps: Array<{ name: string; ok: boolean; stdout?: { skipped?: boolean } }>;
    artifacts: {
      releaseDecision: {
        decision: { status: string };
        inputs: { activeLearningWarningDelta: number };
      };
      promotion: { decisionStatus: string; registerSummary: { registeredVersion: string } };
      traceIndex: { decision: { status: string } | null };
      traceRegistration: { ok: boolean };
      rollbackAudit: { ok: boolean; rollbackCandidates: string[] };
      historyManifest: { totals: { traceIndexes: number }; entries: Array<{ decisionStatus: string | null }> };
    };
  };

  assert.equal(report.ok, true);
  assert.equal(report.artifacts.releaseDecision.decision.status, "manual_review");
  assert.equal(report.artifacts.releaseDecision.inputs.activeLearningWarningDelta, 2);
  assert.equal(report.artifacts.promotion.decisionStatus, "manual_review");
  assert.equal(report.artifacts.promotion.registerSummary.registeredVersion, "nail-texture-seg-v4");
  assert.equal(report.artifacts.traceIndex.decision?.status, "manual_review");
  assert.equal(report.artifacts.traceRegistration.ok, true);
  assert.equal(report.artifacts.rollbackAudit.ok, true);
  assert.deepEqual(report.artifacts.rollbackAudit.rollbackCandidates, ["nail-texture-seg-v3"]);
  assert.equal(report.artifacts.historyManifest.totals.traceIndexes, 1);
  assert.equal(report.artifacts.historyManifest.entries[0]?.decisionStatus, "manual_review");
  assert.equal(report.steps.find((step) => step.name === "promote-approved-release")?.ok, true);
});

test("run-release-governance-pipeline blocks promotion when training dataset readiness explicitly fails", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-release-governance-readiness-"));
  const reportsDir = path.join(root, "reports");
  await mkdir(reportsDir, { recursive: true });
  const trainingReleasePipelineReportPath = path.join(reportsDir, "training-release-pipeline-report.json");
  await writeFile(
    trainingReleasePipelineReportPath,
    JSON.stringify({
      ok: true,
      reportPath: trainingReleasePipelineReportPath,
      artifacts: {
        trainingDatasetReadiness: {
          ok: false,
          outputPath: path.join(reportsDir, "training-dataset-readiness-release.json"),
          authorizationMode: "release",
          steps: [
            { name: "audit-sources-csv", ok: true },
            { name: "audit-training-source-authorization", ok: false },
            { name: "audit-phase1-readiness", ok: false },
          ],
          totals: { images: 25, validMasks: 90 },
        },
        manifest: { version: "nail-texture-seg-v5", modelFile: "nail-texture-seg-v5.onnx" },
        finalAudit: { ok: true, decision: { status: "pass", summary: "audit ok", nextActions: [] } },
      },
      steps: [],
    }),
    "utf8"
  );
  try {
    await execFileAsync(
      process.execPath,
      ["--no-warnings", "--experimental-strip-types", "scripts/run-release-governance-pipeline.ts", "--training-release-pipeline-report", trainingReleasePipelineReportPath],
      { cwd: path.resolve(".") }
    );
    assert.fail("expected governance pipeline to hold a non-ready training dataset");
  } catch (error) {
    const execError = error as Error & { stdout?: string };
    const report = JSON.parse(execError.stdout ?? "{}") as {
      ok: boolean;
      steps: Array<{ name: string; stdout?: { skipped?: boolean } }>;
      artifacts: {
        releaseDecision: { decision: { status: string; reasons: string[] } };
        traceIndex: { trainingReadiness: { ok: boolean; gates: { sourceAuthorization: boolean } } | null };
      };
    };
    assert.equal(report.ok, false);
    assert.equal(report.artifacts.releaseDecision.decision.status, "hold_candidate");
    assert.ok(report.artifacts.releaseDecision.decision.reasons.some((reason) => reason.includes("training dataset readiness failed")));
    assert.equal(report.steps.find((step) => step.name === "promote-approved-release")?.stdout?.skipped, true);
    assert.equal(report.artifacts.traceIndex.trainingReadiness?.ok, false);
    assert.equal(report.artifacts.traceIndex.trainingReadiness?.gates.sourceAuthorization, false);
  }
});
test("run-release-governance-pipeline blocks promotion below the Phase 2 extraction-rate threshold", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-release-governance-extraction-rate-"));
  const reportsDir = path.join(root, "reports");
  await mkdir(reportsDir, { recursive: true });
  const trainingReleasePipelineReportPath = path.join(reportsDir, "training-release-pipeline-report.json");
  await writeFile(
    trainingReleasePipelineReportPath,
    JSON.stringify({
      ok: true,
      reportPath: trainingReleasePipelineReportPath,
      artifacts: {
        manifest: { version: "nail-texture-seg-v6", modelFile: "nail-texture-seg-v6.onnx" },
        finalAudit: { ok: true, decision: { status: "pass", summary: "audit ok", nextActions: [] } },
        finalAuditTextureQualityGate: {
          ok: false,
          totals: { documents: 20, candidatesWithDebug: 100, directlyUsableCandidates: 75 },
          rates: { directlyUsableRate: 0.75, contaminationRate: 0.05, roughRectangleRate: 0.1 },
          evidence: {
            ok: true,
            scope: "release-test-split",
            representativeTestSplit: true,
            documentsOk: true,
            candidatesWithDebugOk: true,
            candidatesWithPolygonOk: true,
            minDocuments: 20,
            minCandidatesWithDebug: 100,
            minCandidatesWithPolygon: 100,
          },
        },
      },
      steps: [],
    }),
    "utf8"
  );

  try {
    await execFileAsync(
      process.execPath,
      ["--no-warnings", "--experimental-strip-types", "scripts/run-release-governance-pipeline.ts", "--training-release-pipeline-report", trainingReleasePipelineReportPath],
      { cwd: path.resolve(".") }
    );
    assert.fail("expected governance to hold extraction rate below 80%");
  } catch (error) {
    const execError = error as Error & { stdout?: string };
    const report = JSON.parse(execError.stdout ?? "{}") as {
      ok: boolean;
      steps: Array<{ name: string; stdout?: { skipped?: boolean } }>;
      artifacts: {
        releaseDecision: {
          decision: { status: string; reasons: string[] };
          inputs: {
            phase2ExtractionRateOk: boolean | null;
            phase2ExtractionEvidenceOk: boolean | null;
            phase2ExtractionEvidenceScope: string | null;
            directlyUsableRate: number | null;
          };
        };        traceIndex: {
          quality: {
            phase2ExtractionRateOk: boolean | null;
            directlyUsableRate: number | null;
            phase2ExtractionEvidenceOk: boolean | null;
            phase2ExtractionEvidenceScope: string | null;
            phase2RequiredUsableRate: number;
          } | null;
        };
      };
    };
    assert.equal(report.ok, false);
    assert.equal(report.artifacts.releaseDecision.decision.status, "hold_candidate");
    assert.equal(report.artifacts.releaseDecision.inputs.phase2ExtractionRateOk, false);
    assert.equal(report.artifacts.releaseDecision.inputs.phase2ExtractionEvidenceOk, true);
    assert.equal(report.artifacts.releaseDecision.inputs.phase2ExtractionEvidenceScope, "release-test-split");
    assert.equal(report.artifacts.releaseDecision.inputs.directlyUsableRate, 0.75);
    assert.equal(report.artifacts.traceIndex.quality?.phase2ExtractionRateOk, false);
    assert.equal(report.artifacts.traceIndex.quality?.directlyUsableRate, 0.75);
    assert.equal(report.artifacts.traceIndex.quality?.phase2ExtractionEvidenceOk, true);
    assert.equal(report.artifacts.traceIndex.quality?.phase2ExtractionEvidenceScope, "release-test-split");
    assert.equal(report.artifacts.traceIndex.quality?.phase2RequiredUsableRate, 0.8);
    assert.ok(report.artifacts.releaseDecision.decision.reasons.some((item) => item.includes("below required 0.800")));
    assert.equal(report.steps.find((step) => step.name === "promote-approved-release")?.stdout?.skipped, true);
  }
});
test("run-release-governance-pipeline blocks promotion when recognition performance fails", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-release-governance-performance-"));
  const reportsDir = path.join(root, "reports");
  await mkdir(reportsDir, { recursive: true });
  const trainingReleasePipelineReportPath = path.join(reportsDir, "training-release-pipeline-report.json");
  const performanceReportPath = path.join(reportsDir, "performance-report.desktop.json");
  await writeFile(
    trainingReleasePipelineReportPath,
    JSON.stringify({
      ok: true,
      reportPath: trainingReleasePipelineReportPath,
      artifacts: {
        manifest: { version: "nail-texture-seg-v8", modelFile: "nail-texture-seg-v8.onnx" },
        finalAudit: { ok: true, decision: { status: "pass", summary: "audit ok", nextActions: [] } },
        finalAuditTextureQualityGate: {
          ok: true,
          totals: { documents: 20, candidatesWithDebug: 100, directlyUsableCandidates: 95 },
          rates: { directlyUsableRate: 0.95, contaminationRate: 0.02, roughRectangleRate: 0.05 },
          evidence: {
            ok: true,
            scope: "release-test-split",
            representativeTestSplit: true,
            documentsOk: true,
            candidatesWithDebugOk: true,
            candidatesWithPolygonOk: true,
          },
        },
      },
      steps: [],
    }),
    "utf8"
  );
  await writeFile(
    performanceReportPath,
    JSON.stringify({
      ok: false,
      profile: "desktop",
      thresholds: { maxElapsedMs: 800, minSamples: 3 },
      totals: { samples: 3, slowSamples: 1, skippedFiles: 0 },
      stats: { averageMs: 700, p95Ms: 920, maxMs: 920 },
      errors: ["1 sample(s) exceeded desktop budget 800ms"],
    }),
    "utf8"
  );

  await assert.rejects(
    execFileAsync(
      process.execPath,
      [
        "--no-warnings",
        "--experimental-strip-types",
        "scripts/run-release-governance-pipeline.ts",
        "--training-release-pipeline-report",
        trainingReleasePipelineReportPath,
        "--performance-report",
        performanceReportPath,
      ],
      { cwd: path.resolve(".") }
    ),
    (error: unknown) => {
      const execError = error as Error & { stdout?: string };
      const report = JSON.parse(execError.stdout ?? "{}") as {
        ok: boolean;
        inputs: { performanceReportPath: string | null };
        steps: Array<{ name: string; stdout?: { skipped?: boolean } }>;
        artifacts: {
          releaseDecision: {
            decision: { status: string; reasons: string[] };
            inputs: { recognitionPerformanceOk: boolean | null; recognitionPerformanceP95Ms: number | null };
          };
          traceIndex: {
            performance: {
              ok: boolean | null;
              profile: string | null;
              maxElapsedMs: number | null;
              p95Ms: number | null;
              slowSamples: number | null;
              performanceReportPath: string | null;
            } | null;
          };
        };
      };
      assert.equal(report.ok, false);
      assert.equal(report.inputs.performanceReportPath, performanceReportPath);
      assert.equal(report.artifacts.releaseDecision.decision.status, "hold_candidate");
      assert.equal(report.artifacts.releaseDecision.inputs.recognitionPerformanceOk, false);
      assert.equal(report.artifacts.releaseDecision.inputs.recognitionPerformanceP95Ms, 920);
      assert.equal(report.artifacts.traceIndex.performance?.ok, false);
      assert.equal(report.artifacts.traceIndex.performance?.profile, "desktop");
      assert.equal(report.artifacts.traceIndex.performance?.maxElapsedMs, 800);
      assert.equal(report.artifacts.traceIndex.performance?.p95Ms, 920);
      assert.equal(report.artifacts.traceIndex.performance?.slowSamples, 1);
      assert.equal(report.artifacts.traceIndex.performance?.performanceReportPath, performanceReportPath);
      assert.ok(report.artifacts.releaseDecision.decision.reasons.some((item) => item.includes("recognition performance failed")));
      assert.equal(report.steps.find((step) => step.name === "promote-approved-release")?.stdout?.skipped, true);
      return true;
    }
  );
});
