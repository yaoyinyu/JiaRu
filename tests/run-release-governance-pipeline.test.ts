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
        inputs: { textureQualityGateOk: boolean | null; directlyUsableRate: number | null };
      };
      promotion: { registerSummary: { registeredVersion: string } };
      traceIndex: { links: { sourceGroupToCandidateVersion: string | null } };
      historyManifest: { totals: { traceIndexes: number } };
    };
  };
  assert.equal(report.ok, true);
  assert.deepEqual(report.steps.map((step) => step.name), [
    "build-release-decision-report",
    "promote-approved-release",
    "build-release-trace-index",
    "register-release-trace-index",
  ]);
  assert.equal(report.artifacts.releaseDecision.decision.status, "approve_candidate");
  assert.equal(report.artifacts.releaseDecision.inputs.textureQualityGateOk, true);
  assert.equal(report.artifacts.releaseDecision.inputs.directlyUsableRate, 0.85);
  assert.equal(report.artifacts.promotion.registerSummary.registeredVersion, "nail-texture-seg-v2");
  assert.equal(
    report.artifacts.traceIndex.links.sourceGroupToCandidateVersion,
    "seed-batch-010 -> nail-texture-seg-v2"
  );
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
      };
    };
    assert.equal(report.ok, false);
    assert.equal(report.artifacts.releaseDecision.decision.status, "hold_candidate");
    assert.equal(report.steps[1]?.name, "promote-approved-release");
    assert.equal(report.steps[1]?.stdout?.skipped, true);
    assert.equal(report.artifacts.traceIndex.batch?.sourceGroup, "seed-batch-011");
    assert.equal(report.steps[3]?.name, "register-release-trace-index");
    assert.equal(report.steps[3]?.stdout?.skipped, true);
  }
});
