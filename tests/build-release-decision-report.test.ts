import assert from "node:assert/strict";
import { execFile } from "node:child_process";
import { mkdtemp, mkdir, readFile, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { promisify } from "node:util";
import test from "node:test";

const execFileAsync = promisify(execFile);

test("build-release-decision-report approves candidate when pipeline and compare both pass cleanly", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-release-decision-pass-"));
  const reportsDir = path.join(root, "reports");
  await mkdir(reportsDir, { recursive: true });

  const pipelineReportPath = path.join(reportsDir, "training-release-pipeline-report.json");
  await writeFile(
    pipelineReportPath,
    JSON.stringify(
      {
        ok: true,
        artifacts: {
          manifest: { version: "nail-texture-seg-v2", modelFile: "nail-texture-seg-v2.onnx" },
          metrics: { seg_map50: 0.8, box_map50: 0.9 },
          finalAudit: {
            ok: true,
            decision: { status: "pass", summary: "all good", nextActions: [] },
          },
          finalAuditFailureSummary: {
            totals: { derivedAnnotationFailures: 0, inferredRecordFailure: 0, csvRows: 0 },
            categoryCounts: {},
          },
          finalAuditTextureQualityGate: {
            ok: true,
            directlyUsableCount: 19,
            directlyUsableRate: 0.95,
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
        improvements: ["seg_map50 improved by 0.01"],
        warnings: [],
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
        currentVersion: "nail-texture-seg-v1",
        releases: [{ version: "nail-texture-seg-v1" }],
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
      "scripts/build-release-decision-report.ts",
      "--pipeline-report",
      pipelineReportPath,
      "--compare-summary",
      compareSummaryPath,
      "--registry",
      registryPath,
    ],
    { cwd: path.resolve(".") }
  );

  const report = JSON.parse(stdout) as {
    ok: boolean;
    decision: { status: string };
    registryCurrentVersion: string | null;
    candidateVersion: string | null;
  };
  assert.equal(report.ok, true);
  assert.equal(report.decision.status, "approve_candidate");
  assert.equal(report.registryCurrentVersion, "nail-texture-seg-v1");
  assert.equal(report.candidateVersion, "nail-texture-seg-v2");
});

test("build-release-decision-report requires manual review when texture quality gate fails despite passing core gates", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-release-decision-texture-gate-"));
  const reportsDir = path.join(root, "reports");
  await mkdir(reportsDir, { recursive: true });

  const pipelineReportPath = path.join(reportsDir, "training-release-pipeline-report.json");
  await writeFile(
    pipelineReportPath,
    JSON.stringify(
      {
        ok: true,
        artifacts: {
          manifest: { version: "nail-texture-seg-v3", modelFile: "nail-texture-seg-v3.onnx" },
          metrics: { seg_map50: 0.82, box_map50: 0.91 },
          finalAudit: {
            ok: true,
            decision: { status: "pass", summary: "all good", nextActions: [] },
          },
          finalAuditFailureSummary: {
            totals: { derivedAnnotationFailures: 0, inferredRecordFailure: 0, csvRows: 0 },
            categoryCounts: {},
          },
          finalAuditTextureQualityGate: {
            ok: false,
            totals: {
              documents: 20,
              candidatesWithDebug: 100,
              directlyUsableCandidates: 82,
              contaminatedCandidates: 6,
            },
            rates: {
              directlyUsableRate: 0.82,
              contaminationRate: 0.06,
              roughRectangleRate: 0.2,
            },
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
            warningBreakdown: { dirty_mask_crop: 6 },
            warnings: ["texture quality gate failed"],
            nextSteps: ["review low-quality texture crops"],
          },
        },
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

  const { stdout } = await execFileAsync(
    process.execPath,
    [
      "--no-warnings",
      "--experimental-strip-types",
      "scripts/build-release-decision-report.ts",
      "--pipeline-report",
      pipelineReportPath,
      "--compare-summary",
      compareSummaryPath,
    ],
    { cwd: path.resolve(".") }
  );

  const report = JSON.parse(stdout) as {
    ok: boolean;
    decision: { status: string; reasons: string[]; nextActions: string[] };
    inputs: {
      textureQualityGateOk: boolean | null;
      phase2ExtractionRateOk: boolean | null;
      directlyUsableRate: number | null;
      contaminationRate: number | null;
    };
    artifacts: {
      finalAuditTextureQualityGate: { totals: { contaminatedCandidates: number } } | null;
    };
  };
  assert.equal(report.ok, true);
  assert.equal(report.decision.status, "manual_review");
  assert.equal(report.inputs.textureQualityGateOk, false);
  assert.equal(report.inputs.phase2ExtractionRateOk, true);
  assert.equal(report.inputs.directlyUsableRate, 0.82);
  assert.equal(report.inputs.contaminationRate, 0.06);
  assert.equal(report.artifacts.finalAuditTextureQualityGate?.totals.contaminatedCandidates, 6);
  assert.ok(report.decision.reasons.some((item) => item.includes("texture quality gate failed")));
  assert.ok(report.decision.nextActions.some((item) => item.includes("low-quality texture crops")));
});

test("build-release-decision-report holds candidate when compare regresses or final audit is blocked", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-release-decision-hold-"));
  const reportsDir = path.join(root, "reports");
  await mkdir(reportsDir, { recursive: true });

  const pipelineReportPath = path.join(reportsDir, "training-release-pipeline-report.json");
  await writeFile(
    pipelineReportPath,
    JSON.stringify(
      {
        ok: false,
        artifacts: {
          manifest: { version: "nail-texture-seg-v2", modelFile: "nail-texture-seg-v2.onnx" },
          finalAudit: {
            ok: false,
            decision: { status: "blocked", summary: "artifact missing", nextActions: ["fix model"] },
          },
          finalAuditFailureSummary: {
            totals: { derivedAnnotationFailures: 3, inferredRecordFailure: 1, csvRows: 0 },
            categoryCounts: { postprocess: 3 },
          },
        },
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
        ok: false,
        regressions: ["seg_map50 regressed by -0.05"],
        improvements: [],
        warnings: [],
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
        "scripts/build-release-decision-report.ts",
        "--pipeline-report",
        pipelineReportPath,
        "--compare-summary",
        compareSummaryPath,
      ],
      { cwd: path.resolve(".") }
    );
    assert.fail("expected build-release-decision-report to exit non-zero");
  } catch (error) {
    const execError = error as Error & { stdout?: string };
    const report = JSON.parse(execError.stdout ?? "{}") as {
      ok: boolean;
      decision: { status: string; reasons: string[] };
      inputs: { postprocessFailures: number };
      outputPath: string;
    };
    assert.equal(report.ok, false);
    assert.equal(report.decision.status, "hold_candidate");
    assert.equal(report.inputs.postprocessFailures, 3);
    assert.ok(report.decision.reasons.some((item) => item.includes("training release pipeline did not pass")));
    assert.ok(report.decision.reasons.some((item) => item.includes("final audit status is blocked")));
    const saved = JSON.parse(await readFile(report.outputPath, "utf8")) as {
      decision: { status: string };
    };
    assert.equal(saved.decision.status, "hold_candidate");
  }
});

test("build-release-decision-report holds an otherwise passing candidate when training data is not release-ready", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-release-decision-readiness-"));
  const reportsDir = path.join(root, "reports");
  await mkdir(reportsDir, { recursive: true });
  const pipelineReportPath = path.join(reportsDir, "training-release-pipeline-report.json");
  await writeFile(
    pipelineReportPath,
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
        finalAudit: { ok: true, decision: { status: "pass", summary: "all good", nextActions: [] } },
      },
    }),
    "utf8"
  );
  try {
    await execFileAsync(
      process.execPath,
      ["--no-warnings", "--experimental-strip-types", "scripts/build-release-decision-report.ts", "--pipeline-report", pipelineReportPath],
      { cwd: path.resolve(".") }
    );
    assert.fail("expected non-ready training data to hold the candidate");
  } catch (error) {
    const execError = error as Error & { stdout?: string };
    const report = JSON.parse(execError.stdout ?? "{}") as {
      ok: boolean;
      decision: { status: string; reasons: string[]; nextActions: string[] };
      inputs: { trainingDatasetReadinessOk: boolean | null };
      artifacts: { trainingDatasetReadiness: { authorizationMode: string; totals: { images: number } } | null };
    };
    assert.equal(report.ok, false);
    assert.equal(report.decision.status, "hold_candidate");
    assert.equal(report.inputs.trainingDatasetReadinessOk, false);
    assert.equal(report.artifacts.trainingDatasetReadiness?.authorizationMode, "release");
    assert.equal(report.artifacts.trainingDatasetReadiness?.totals.images, 25);
    assert.ok(report.decision.reasons.some((reason) => reason.includes("training dataset readiness failed") && reason.includes("audit-training-source-authorization")));
    assert.ok(report.decision.nextActions.some((action) => action.includes("source provenance")));
  }
});
test("build-release-decision-report hard-holds a candidate below the Phase 2 extraction-rate threshold", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-release-decision-extraction-rate-"));
  const reportsDir = path.join(root, "reports");
  await mkdir(reportsDir, { recursive: true });
  const pipelineReportPath = path.join(reportsDir, "training-release-pipeline-report.json");
  await writeFile(
    pipelineReportPath,
    JSON.stringify({
      ok: true,
      artifacts: {
        manifest: { version: "nail-texture-seg-v6", modelFile: "nail-texture-seg-v6.onnx" },
        finalAudit: {
          ok: true,
          decision: { status: "pass", summary: "all good", nextActions: [] },
        },
        finalAuditTextureQualityGate: {
          ok: false,
          totals: {
            documents: 20,
            candidatesWithDebug: 100,
            directlyUsableCandidates: 75,
          },
          rates: {
            directlyUsableRate: 0.75,
            contaminationRate: 0.05,
            roughRectangleRate: 0.1,
          },
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
          warnings: ["directly usable rate is below target"],
        },
      },
    }),
    "utf8"
  );

  await assert.rejects(
    execFileAsync(
      process.execPath,
      [
        "--no-warnings",
        "--experimental-strip-types",
        "scripts/build-release-decision-report.ts",
        "--pipeline-report",
        pipelineReportPath,
      ],
      { cwd: path.resolve(".") }
    ),
    (error: unknown) => {
      const execError = error as Error & { stdout?: string };
      const report = JSON.parse(execError.stdout ?? "{}") as {
        ok: boolean;
        decision: { status: string; reasons: string[]; nextActions: string[] };
        inputs: {
          phase2ExtractionRateOk: boolean | null;
          directlyUsableRate: number | null;
        };
      };
      assert.equal(report.ok, false);
      assert.equal(report.decision.status, "hold_candidate");
      assert.equal(report.inputs.phase2ExtractionRateOk, false);
      assert.equal(report.inputs.directlyUsableRate, 0.75);
      assert.ok(report.decision.reasons.some((item) => item.includes("below required 0.800")));
      assert.ok(report.decision.nextActions.some((item) => item.includes("at least 80%")));
      return true;
    }
  );
});
test("build-release-decision-report hard-holds passing rates without release-test-split evidence", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-release-decision-evidence-"));
  const reportsDir = path.join(root, "reports");
  await mkdir(reportsDir, { recursive: true });
  const pipelineReportPath = path.join(reportsDir, "training-release-pipeline-report.json");

  await writeFile(
    pipelineReportPath,
    JSON.stringify({
      ok: true,
      artifacts: {
        manifest: { version: "nail-texture-seg-v7", modelFile: "nail-texture-seg-v7.onnx" },
        finalAudit: {
          ok: true,
          decision: { status: "pass", summary: "all good", nextActions: [] },
        },
        finalAuditTextureQualityGate: {
          ok: true,
          totals: { documents: 1, candidatesWithDebug: 6, directlyUsableCandidates: 6 },
          rates: { directlyUsableRate: 1, contaminationRate: 0, roughRectangleRate: 0 },
          evidence: {
            ok: true,
            scope: "local-debug",
            representativeTestSplit: false,
            documentsOk: true,
            candidatesWithDebugOk: true,
            candidatesWithPolygonOk: true,
          },
        },
      },
    }),
    "utf8"
  );

  await assert.rejects(
    execFileAsync(
      process.execPath,
      [
        "--no-warnings",
        "--experimental-strip-types",
        "scripts/build-release-decision-report.ts",
        "--pipeline-report",
        pipelineReportPath,
      ],
      { cwd: path.resolve(".") }
    ),
    (error: unknown) => {
      const execError = error as Error & { stdout?: string };
      const report = JSON.parse(execError.stdout ?? "{}") as {
        ok: boolean;
        decision: { status: string; reasons: string[]; nextActions: string[] };
        inputs: {
          phase2ExtractionRateOk: boolean | null;
          phase2ExtractionEvidenceOk: boolean | null;
          phase2ExtractionEvidenceScope: string | null;
        };
      };
      assert.equal(report.ok, false);
      assert.equal(report.decision.status, "hold_candidate");
      assert.equal(report.inputs.phase2ExtractionRateOk, true);
      assert.equal(report.inputs.phase2ExtractionEvidenceOk, false);
      assert.equal(report.inputs.phase2ExtractionEvidenceScope, "local-debug");
      assert.ok(report.decision.reasons.some((item) => item.includes("not release-ready")));
      assert.ok(report.decision.nextActions.some((item) => item.includes("representative release test split")));
      return true;
    }
  );
});
test("build-release-decision-report hard-holds a candidate when recognition performance fails", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-release-decision-performance-"));
  const reportsDir = path.join(root, "reports");
  await mkdir(reportsDir, { recursive: true });
  const pipelineReportPath = path.join(reportsDir, "training-release-pipeline-report.json");
  const performanceReportPath = path.join(reportsDir, "performance-report.mobile.json");

  await writeFile(
    pipelineReportPath,
    JSON.stringify({
      ok: true,
      artifacts: {
        manifest: { version: "nail-texture-seg-v8", modelFile: "nail-texture-seg-v8.onnx" },
        finalAudit: {
          ok: true,
          decision: { status: "pass", summary: "all good", nextActions: [] },
        },
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
    }),
    "utf8"
  );
  await writeFile(
    performanceReportPath,
    JSON.stringify({
      ok: false,
      profile: "mobile",
      thresholds: { maxElapsedMs: 1500, minSamples: 5 },
      totals: { samples: 5, slowSamples: 2, skippedFiles: 0 },
      stats: { averageMs: 1330, p95Ms: 1800, maxMs: 1900 },
      errors: ["2 sample(s) exceeded mobile budget 1500ms"],
    }),
    "utf8"
  );

  await assert.rejects(
    execFileAsync(
      process.execPath,
      [
        "--no-warnings",
        "--experimental-strip-types",
        "scripts/build-release-decision-report.ts",
        "--pipeline-report",
        pipelineReportPath,
        "--performance-report",
        performanceReportPath,
      ],
      { cwd: path.resolve(".") }
    ),
    (error: unknown) => {
      const execError = error as Error & { stdout?: string };
      const report = JSON.parse(execError.stdout ?? "{}") as {
        ok: boolean;
        performanceReportPath: string | null;
        decision: { status: string; reasons: string[]; nextActions: string[] };
        inputs: {
          recognitionPerformanceOk: boolean | null;
          recognitionPerformanceProfile: string | null;
          recognitionPerformanceMaxElapsedMs: number | null;
          recognitionPerformanceP95Ms: number | null;
          recognitionPerformanceSlowSamples: number | null;
        };
        artifacts: { recognitionPerformance: { profile: string } | null };
      };
      assert.equal(report.ok, false);
      assert.equal(report.performanceReportPath, performanceReportPath);
      assert.equal(report.decision.status, "hold_candidate");
      assert.equal(report.inputs.recognitionPerformanceOk, false);
      assert.equal(report.inputs.recognitionPerformanceProfile, "mobile");
      assert.equal(report.inputs.recognitionPerformanceMaxElapsedMs, 1500);
      assert.equal(report.inputs.recognitionPerformanceP95Ms, 1800);
      assert.equal(report.inputs.recognitionPerformanceSlowSamples, 2);
      assert.equal(report.artifacts.recognitionPerformance?.profile, "mobile");
      assert.ok(report.decision.reasons.some((item) => item.includes("recognition performance failed")));
      assert.ok(report.decision.nextActions.some((item) => item.includes("latency")));
      return true;
    }
  );
});
