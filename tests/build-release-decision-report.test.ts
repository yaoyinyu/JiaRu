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
