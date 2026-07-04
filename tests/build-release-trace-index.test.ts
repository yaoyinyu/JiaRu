import assert from "node:assert/strict";
import { execFile } from "node:child_process";
import { mkdtemp, mkdir, readFile, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { promisify } from "node:util";
import test from "node:test";

const execFileAsync = promisify(execFile);

test("build-release-trace-index links batch release decision promotion and registry artifacts", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-release-trace-index-"));
  const reportsDir = path.join(root, "reports");
  await mkdir(reportsDir, { recursive: true });

  const reviewedBatchImportPipelineReportPath = path.join(
    reportsDir,
    "reviewed-batch-import-pipeline-report.json"
  );
  await writeFile(
    reviewedBatchImportPipelineReportPath,
    JSON.stringify(
      {
        ok: true,
        rootDir: "C:/tmp/seed-batch-001",
        reportPath: reviewedBatchImportPipelineReportPath,
        steps: [
          {
            name: "import-reviewed-batch",
            stdout: {
              sourceGroup: "seed-batch-001",
              datasetRoot: "C:/tmp/dataset",
              reportPath: "C:/tmp/dataset/metadata/reviewed-import-seed-batch-001.report.json",
              importedDocuments: [{ fileName: "sample-001.jpg" }, { fileName: "sample-002.png" }],
            },
          },
        ],
      },
      null,
      2
    ),
    "utf8"
  );

  const trainingReleasePipelineReportPath = path.join(
    reportsDir,
    "training-release-pipeline-report.json"
  );
  await writeFile(
    trainingReleasePipelineReportPath,
    JSON.stringify(
      {
        ok: true,
        paths: {
          manifestPath: "C:/tmp/public/models/nail-texture-seg/manifest.json",
          metricsPath: "C:/tmp/model/exports/nail-texture-seg-v2/metrics.json",
          trainOutputDir: "C:/tmp/model/exports/nail-texture-seg-v2",
        },
        artifacts: {
          manifest: { version: "nail-texture-seg-v2", modelFile: "nail-texture-seg-v2.onnx" },
          finalAudit: { decision: { status: "pass", summary: "ok" } },
          finalAuditFailureSummary: {
            totals: { derivedAnnotationFailures: 2 },
            categoryCounts: { postprocess: 2 },
          },
        },
        steps: [
          {
            name: "run-real-model-final-audit",
            stdout: {
              finalReportPath: "C:/tmp/model/exports/nail-texture-seg-v2/real-model-final-audit/real-model-final-audit-report.json",
              failureSummaryPath: "C:/tmp/model/exports/nail-texture-seg-v2/real-model-final-audit/failure-case-summary.json",
              recordPath: "C:/tmp/model/exports/nail-texture-seg-v2/real-model-final-audit/real-model-first-run-record.json",
            },
          },
        ],
      },
      null,
      2
    ),
    "utf8"
  );

  const releaseDecisionReportPath = path.join(reportsDir, "release-decision-report.json");
  await writeFile(
    releaseDecisionReportPath,
    JSON.stringify(
      {
        pipelineReportPath: trainingReleasePipelineReportPath,
        compareSummaryPath: "C:/tmp/model/exports/nail-texture-seg-v2/compare-summary.json",
        registryPath: "C:/tmp/public/models/nail-texture-seg/release-registry.json",
        outputPath: releaseDecisionReportPath,
        candidateVersion: "nail-texture-seg-v2",
        decision: {
          status: "manual_review",
          summary: "needs review",
        },
        inputs: {
          textureQualityGateOk: false,
          phase2ExtractionRateOk: true,
          phase2ExtractionEvidenceOk: true,
          phase2ExtractionEvidenceScope: "release-test-split",
          directlyUsableRate: 0.82,
          contaminationRate: 0.06,
        },
      },
      null,
      2
    ),
    "utf8"
  );

  const promotionReportPath = path.join(reportsDir, "promotion-report.json");
  await writeFile(
    promotionReportPath,
    JSON.stringify(
      {
        decisionReportPath: releaseDecisionReportPath,
        pipelineReportPath: trainingReleasePipelineReportPath,
        registryPath: "C:/tmp/public/models/nail-texture-seg/release-registry.json",
        outputPath: promotionReportPath,
        candidateVersion: "nail-texture-seg-v2",
        decisionStatus: "manual_review",
        manifestPath: "C:/tmp/public/models/nail-texture-seg/manifest.json",
        registerSummary: {
          currentVersion: "nail-texture-seg-v2",
          registeredVersion: "nail-texture-seg-v2",
          snapshotPath: "C:/tmp/public/models/nail-texture-seg/manifest.nail-texture-seg-v2.json",
        },
      },
      null,
      2
    ),
    "utf8"
  );

  const registryPath = path.join(reportsDir, "release-registry.json");
  await writeFile(
    registryPath,
    JSON.stringify(
      {
        currentVersion: "nail-texture-seg-v2",
        releases: [{ version: "nail-texture-seg-v1" }, { version: "nail-texture-seg-v2" }],
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
      "scripts/build-release-trace-index.ts",
      "--reviewed-batch-import-pipeline-report",
      reviewedBatchImportPipelineReportPath,
      "--training-release-pipeline-report",
      trainingReleasePipelineReportPath,
      "--release-decision-report",
      releaseDecisionReportPath,
      "--promotion-report",
      promotionReportPath,
      "--registry",
      registryPath,
    ],
    { cwd: path.resolve(".") }
  );

  const summary = JSON.parse(stdout) as {
    candidateVersion: string | null;
    currentRegistryVersion: string | null;
    batch: { sourceGroup: string | null; importedFileCount: number } | null;
    release: { finalAuditStatus: string | null; derivedAnnotationFailures: number };
    quality: {
      phase2ExtractionRateOk: boolean | null;
      directlyUsableRate: number | null;
      phase2ExtractionEvidenceOk: boolean | null;
      phase2ExtractionEvidenceScope: string | null;
      phase2RequiredUsableRate: number;
      phase4TextureQualityGateOk: boolean | null;
      contaminationRate: number | null;
    } | null;
    decision: { status: string } | null;
    promotion: { registeredVersion: string | null } | null;
    registry: { releaseCount: number } | null;
    links: { sourceGroupToCandidateVersion: string | null };
    outputPath: string;
  };

  assert.equal(summary.candidateVersion, "nail-texture-seg-v2");
  assert.equal(summary.currentRegistryVersion, "nail-texture-seg-v2");
  assert.equal(summary.batch?.sourceGroup, "seed-batch-001");
  assert.equal(summary.batch?.importedFileCount, 2);
  assert.equal(summary.release.finalAuditStatus, "pass");
  assert.equal(summary.release.derivedAnnotationFailures, 2);
  assert.equal(summary.quality?.phase2ExtractionRateOk, true);
  assert.equal(summary.quality?.directlyUsableRate, 0.82);
  assert.equal(summary.quality?.phase2ExtractionEvidenceOk, true);
  assert.equal(summary.quality?.phase2ExtractionEvidenceScope, "release-test-split");
  assert.equal(summary.quality?.phase2RequiredUsableRate, 0.8);
  assert.equal(summary.quality?.phase4TextureQualityGateOk, false);
  assert.equal(summary.quality?.contaminationRate, 0.06);
  assert.equal(summary.decision?.status, "manual_review");
  assert.equal(summary.promotion?.registeredVersion, "nail-texture-seg-v2");
  assert.equal(summary.registry?.releaseCount, 2);
  assert.equal(summary.links.sourceGroupToCandidateVersion, "seed-batch-001 -> nail-texture-seg-v2");

  const saved = JSON.parse(await readFile(summary.outputPath, "utf8")) as {
    candidateVersion: string | null;
  };
  assert.equal(saved.candidateVersion, "nail-texture-seg-v2");
});

test("build-release-trace-index can upgrade an initial draft into a formal trace", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-release-trace-index-from-draft-"));
  const reportsDir = path.join(root, "reports");
  await mkdir(reportsDir, { recursive: true });

  const releaseTraceDraftPath = path.join(reportsDir, "release-trace-draft.json");
  await writeFile(
    releaseTraceDraftPath,
    JSON.stringify(
      {
        draft: true,
        batch: {
          rootDir: "C:/tmp/seed-batch-003",
          sourceGroup: "seed-batch-003",
          datasetRoot: "C:/tmp/dataset",
          reviewedImportReportPath: "C:/tmp/dataset/metadata/reviewed-import-seed-batch-003.report.json",
          importedFileCount: 4,
        },
      },
      null,
      2
    ),
    "utf8"
  );

  const trainingReleasePipelineReportPath = path.join(
    reportsDir,
    "training-release-pipeline-report.json"
  );
  await writeFile(
    trainingReleasePipelineReportPath,
    JSON.stringify(
      {
        ok: true,
        paths: {
          manifestPath: "C:/tmp/public/models/nail-texture-seg/manifest.json",
          metricsPath: "C:/tmp/model/exports/nail-texture-seg-v3/metrics.json",
          trainOutputDir: "C:/tmp/model/exports/nail-texture-seg-v3",
        },
        artifacts: {
          manifest: { version: "nail-texture-seg-v3", modelFile: "nail-texture-seg-v3.onnx" },
          finalAudit: { decision: { status: "pass", summary: "ok" } },
          finalAuditFailureSummary: {
            totals: { derivedAnnotationFailures: 0 },
            categoryCounts: { postprocess: 0 },
          },
        },
        steps: [
          {
            name: "run-real-model-final-audit",
            stdout: {
              finalReportPath: "C:/tmp/model/exports/nail-texture-seg-v3/real-model-final-audit/real-model-final-audit-report.json",
              failureSummaryPath: "C:/tmp/model/exports/nail-texture-seg-v3/real-model-final-audit/failure-case-summary.json",
              recordPath: "C:/tmp/model/exports/nail-texture-seg-v3/real-model-final-audit/real-model-first-run-record.json",
            },
          },
        ],
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
      "scripts/build-release-trace-index.ts",
      "--release-trace-draft",
      releaseTraceDraftPath,
      "--training-release-pipeline-report",
      trainingReleasePipelineReportPath,
    ],
    { cwd: path.resolve(".") }
  );

  const summary = JSON.parse(stdout) as {
    candidateVersion: string | null;
    batch: {
      sourceGroup: string | null;
      importedFileCount: number;
      releaseTraceDraftPath: string | null;
    } | null;
    links: { sourceGroupToCandidateVersion: string | null };
  };

  assert.equal(summary.candidateVersion, "nail-texture-seg-v3");
  assert.equal(summary.batch?.sourceGroup, "seed-batch-003");
  assert.equal(summary.batch?.importedFileCount, 4);
  assert.equal(summary.batch?.releaseTraceDraftPath, releaseTraceDraftPath);
  assert.equal(summary.links.sourceGroupToCandidateVersion, "seed-batch-003 -> nail-texture-seg-v3");
});

test("build-release-trace-index preserves active learning trace details from release trace draft", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-release-trace-index-active-learning-"));
  const reportsDir = path.join(root, "reports");
  await mkdir(reportsDir, { recursive: true });

  const releaseTraceDraftPath = path.join(reportsDir, "active-learning-release-trace-draft.json");
  await writeFile(
    releaseTraceDraftPath,
    JSON.stringify(
      {
        draft: true,
        activeLearning: {
          pipelineReportPath: "C:/tmp/debug-sample-active-learning-pipeline-report.json",
          sampleDir: "C:/tmp/debug-samples",
          imageDir: "C:/tmp/debug-images",
          priorityReportPath: "C:/tmp/prioritized-debug-samples.json",
          priorityFilters: {
            reportPath: "C:/tmp/prioritized-debug-samples.json",
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
            reasonBreakdown: { manual_candidate_added: 3, high_confidence_deleted: 1 },
          },
          readinessSnapshot: {
            reportPath: "C:/tmp/phase1-readiness.json",
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

  const trainingReleasePipelineReportPath = path.join(
    reportsDir,
    "training-release-pipeline-report.json"
  );
  await writeFile(
    trainingReleasePipelineReportPath,
    JSON.stringify(
      {
        ok: true,
        paths: {
          manifestPath: "C:/tmp/public/models/nail-texture-seg/manifest.json",
          metricsPath: "C:/tmp/model/exports/nail-texture-seg-v4/metrics.json",
          trainOutputDir: "C:/tmp/model/exports/nail-texture-seg-v4",
        },
        artifacts: {
          manifest: { version: "nail-texture-seg-v4", modelFile: "nail-texture-seg-v4.onnx" },
          finalAudit: { decision: { status: "pass", summary: "ok" } },
          finalAuditFailureSummary: {
            totals: { derivedAnnotationFailures: 0 },
            categoryCounts: { postprocess: 0 },
          },
        },
        steps: [],
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
      "scripts/build-release-trace-index.ts",
      "--release-trace-draft",
      releaseTraceDraftPath,
      "--training-release-pipeline-report",
      trainingReleasePipelineReportPath,
    ],
    { cwd: path.resolve(".") }
  );

  const summary = JSON.parse(stdout) as {
    candidateVersion: string | null;
    activeLearning: {
      importedSampleCount: number;
      importedByPriority: { high: number; medium: number };
      prioritySummary: { backendBreakdown: Record<string, number> } | null;
      priorityFilters: { minPriorityTier: string | null; top: number | null } | null;
      readinessSnapshot: { totals: { images: number; validMasks: number } | null } | null;
    } | null;
  };

  assert.equal(summary.candidateVersion, "nail-texture-seg-v4");
  assert.equal(summary.activeLearning?.importedSampleCount, 5);
  assert.equal(summary.activeLearning?.importedByPriority.high, 3);
  assert.equal(summary.activeLearning?.importedByPriority.medium, 2);
  assert.deepEqual(summary.activeLearning?.prioritySummary?.backendBreakdown, {
    fallback: 4,
    model: 1,
  });
  assert.equal(summary.activeLearning?.priorityFilters?.minPriorityTier, "medium");
  assert.equal(summary.activeLearning?.priorityFilters?.top, 20);
  assert.equal(summary.activeLearning?.readinessSnapshot?.totals?.images, 25);
  assert.equal(summary.activeLearning?.readinessSnapshot?.totals?.validMasks, 90);
});



test("build-release-trace-index preserves authoritative training readiness from the training pipeline", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-release-trace-readiness-"));
  const reportsDir = path.join(root, "reports");
  await mkdir(reportsDir, { recursive: true });
  const trainingReleasePipelineReportPath = path.join(reportsDir, "training-release-pipeline-report.json");
  await writeFile(
    trainingReleasePipelineReportPath,
    JSON.stringify({
      ok: true,
      artifacts: {
        trainingDatasetReadiness: {
          ok: false,
          outputPath: "C:/tmp/training-dataset-readiness-release.json",
          authorizationMode: "release",
          steps: [
            { name: "audit-sources-csv", ok: true },
            { name: "audit-training-source-authorization", ok: false },
            { name: "audit-phase1-readiness", ok: false },
          ],
          totals: { images: 25, validMasks: 90 },
        },
        manifest: { version: "nail-texture-seg-v5", modelFile: "nail-texture-seg-v5.onnx" },
        finalAudit: { decision: { status: "pass", summary: "ok" } },
      },
      steps: [],
    }),
    "utf8"
  );
  const { stdout } = await execFileAsync(
    process.execPath,
    ["--no-warnings", "--experimental-strip-types", "scripts/build-release-trace-index.ts", "--training-release-pipeline-report", trainingReleasePipelineReportPath],
    { cwd: path.resolve(".") }
  );
  const summary = JSON.parse(stdout) as {
    trainingReadiness: {
      ok: boolean | null;
      authorizationMode: string | null;
      gates: { sourceAudit: boolean | null; sourceAuthorization: boolean | null; phase1Readiness: boolean | null };
      totals: { images: number | null; validMasks: number | null };
      failingSteps: string[];
    } | null;
  };
  assert.equal(summary.trainingReadiness?.ok, false);
  assert.equal(summary.trainingReadiness?.authorizationMode, "release");
  assert.equal(summary.trainingReadiness?.gates.sourceAudit, true);
  assert.equal(summary.trainingReadiness?.gates.sourceAuthorization, false);
  assert.equal(summary.trainingReadiness?.gates.phase1Readiness, false);
  assert.equal(summary.trainingReadiness?.totals.images, 25);
  assert.equal(summary.trainingReadiness?.totals.validMasks, 90);
  assert.deepEqual(summary.trainingReadiness?.failingSteps, ["audit-training-source-authorization", "audit-phase1-readiness"]);
});