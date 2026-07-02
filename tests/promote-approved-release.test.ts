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

test("promote-approved-release registers candidate when decision report is approve_candidate", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-promote-approved-"));
  const modelDir = path.join(root, "public", "models", "nail-texture-seg");
  const reportsDir = path.join(root, "reports");
  await mkdir(modelDir, { recursive: true });
  await mkdir(reportsDir, { recursive: true });

  const manifestPath = await createManifest(modelDir, "nail-texture-seg-v2");
  const pipelineReportPath = path.join(reportsDir, "training-release-pipeline-report.json");
  await writeFile(
    pipelineReportPath,
    JSON.stringify(
      {
        paths: {
          manifestPath,
        },
      },
      null,
      2
    ),
    "utf8"
  );

  const decisionReportPath = path.join(reportsDir, "release-decision-report.json");
  await writeFile(
    decisionReportPath,
    JSON.stringify(
      {
        pipelineReportPath,
        candidateVersion: "nail-texture-seg-v2",
        decision: {
          status: "approve_candidate",
          summary: "ok",
          reasons: [],
          nextActions: ["register it"],
        },
      },
      null,
      2
    ),
    "utf8"
  );

  const registryPath = path.join(modelDir, "release-registry.json");
  const { stdout } = await execFileAsync(
    process.execPath,
    [
      "--no-warnings",
      "--experimental-strip-types",
      "scripts/promote-approved-release.ts",
      "--decision-report",
      decisionReportPath,
      "--registry",
      registryPath,
    ],
    { cwd: path.resolve(".") }
  );

  const summary = JSON.parse(stdout) as {
    ok: boolean;
    registerSummary: { registeredVersion: string; currentVersion: string | null };
  };
  assert.equal(summary.ok, true);
  assert.equal(summary.registerSummary.registeredVersion, "nail-texture-seg-v2");
  assert.equal(summary.registerSummary.currentVersion, "nail-texture-seg-v2");
});

test("promote-approved-release can auto-register a formal trace into release history after promotion", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-promote-trace-register-"));
  const modelDir = path.join(root, "public", "models", "nail-texture-seg");
  const reportsDir = path.join(root, "reports");
  await mkdir(modelDir, { recursive: true });
  await mkdir(reportsDir, { recursive: true });

  const manifestPath = await createManifest(modelDir, "nail-texture-seg-v2");
  const pipelineReportPath = path.join(reportsDir, "training-release-pipeline-report.json");
  await writeFile(
    pipelineReportPath,
    JSON.stringify(
      {
        paths: {
          manifestPath,
        },
      },
      null,
      2
    ),
    "utf8"
  );

  const decisionReportPath = path.join(reportsDir, "release-decision-report.json");
  await writeFile(
    decisionReportPath,
    JSON.stringify(
      {
        pipelineReportPath,
        candidateVersion: "nail-texture-seg-v2",
        decision: {
          status: "approve_candidate",
          summary: "ok",
          reasons: [],
          nextActions: ["register it"],
        },
      },
      null,
      2
    ),
    "utf8"
  );

  const traceIndexPath = path.join(reportsDir, "release-trace-index.json");
  await writeFile(
    traceIndexPath,
    JSON.stringify(
      {
        candidateVersion: "nail-texture-seg-v2",
        currentRegistryVersion: null,
        batch: { sourceGroup: "seed-batch-003", datasetRoot: "C:/tmp/dataset", importedFileCount: 4 },
        release: { finalAuditStatus: "pass", derivedAnnotationFailures: 0, postprocessFailures: 0 },
        decision: { status: "approve_candidate", summary: "ok" },
        promotion: { registeredVersion: "nail-texture-seg-v2", currentVersion: "nail-texture-seg-v2" },
      },
      null,
      2
    ),
    "utf8"
  );

  const historyManifestPath = path.join(reportsDir, "release-history-manifest.json");
  const traceRegistrationOutputPath = path.join(reportsDir, "trace-registration-report.json");
  const { stdout } = await execFileAsync(
    process.execPath,
    [
      "--no-warnings",
      "--experimental-strip-types",
      "scripts/promote-approved-release.ts",
      "--decision-report",
      decisionReportPath,
      "--trace-index",
      traceIndexPath,
      "--history-manifest",
      historyManifestPath,
      "--trace-registration-output",
      traceRegistrationOutputPath,
    ],
    { cwd: path.resolve(".") }
  );

  const summary = JSON.parse(stdout) as {
    ok: boolean;
    traceRegistrationSummary: {
      ok: boolean;
      traceIndexPath: string;
      historyManifestPath: string;
      traceIndexCount: number;
    } | null;
  };
  assert.equal(summary.ok, true);
  assert.ok(summary.traceRegistrationSummary);
  assert.equal(summary.traceRegistrationSummary?.ok, true);
  assert.equal(summary.traceRegistrationSummary?.traceIndexPath, traceIndexPath);
  assert.equal(summary.traceRegistrationSummary?.historyManifestPath, historyManifestPath);
  assert.equal(summary.traceRegistrationSummary?.traceIndexCount, 1);

  const savedHistory = JSON.parse(await readFile(historyManifestPath, "utf8")) as {
    totals: { traceIndexes: number };
    entries: Array<{
      candidateVersion: string | null;
      traceIndexPath: string | null;
      decisionStatus: string | null;
      registeredVersion: string | null;
    }>;
  };
  assert.equal(savedHistory.totals.traceIndexes, 1);
  assert.equal(savedHistory.entries.length, 1);
  assert.equal(savedHistory.entries[0]?.candidateVersion, "nail-texture-seg-v2");
  assert.equal(savedHistory.entries[0]?.traceIndexPath, traceIndexPath);
  assert.equal(savedHistory.entries[0]?.decisionStatus, "approve_candidate");
  assert.equal(savedHistory.entries[0]?.registeredVersion, "nail-texture-seg-v2");
});

test("promote-approved-release blocks hold_candidate decisions", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-promote-hold-"));
  const modelDir = path.join(root, "public", "models", "nail-texture-seg");
  const reportsDir = path.join(root, "reports");
  await mkdir(modelDir, { recursive: true });
  await mkdir(reportsDir, { recursive: true });

  const manifestPath = await createManifest(modelDir, "nail-texture-seg-v2");
  const pipelineReportPath = path.join(reportsDir, "training-release-pipeline-report.json");
  await writeFile(
    pipelineReportPath,
    JSON.stringify(
      {
        paths: {
          manifestPath,
        },
      },
      null,
      2
    ),
    "utf8"
  );

  const decisionReportPath = path.join(reportsDir, "release-decision-report.json");
  await writeFile(
    decisionReportPath,
    JSON.stringify(
      {
        pipelineReportPath,
        candidateVersion: "nail-texture-seg-v2",
        decision: {
          status: "hold_candidate",
          summary: "blocked",
          reasons: ["compare regressed"],
          nextActions: ["keep baseline"],
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
        "scripts/promote-approved-release.ts",
        "--decision-report",
        decisionReportPath,
      ],
      { cwd: path.resolve(".") }
    );
    assert.fail("expected promote-approved-release to exit non-zero for hold_candidate");
  } catch (error) {
    const execError = error as Error & { stdout?: string };
    const summary = JSON.parse(execError.stdout ?? "{}") as {
      ok: boolean;
      decisionStatus: string;
      reason: string;
      outputPath: string;
    };
    assert.equal(summary.ok, false);
    assert.equal(summary.decisionStatus, "hold_candidate");
    assert.ok(summary.reason.includes("hold_candidate"));
    const saved = JSON.parse(await readFile(summary.outputPath, "utf8")) as {
      decisionStatus: string;
    };
    assert.equal(saved.decisionStatus, "hold_candidate");
  }
});

test("promote-approved-release can allow manual_review decisions when explicitly authorized", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-promote-manual-"));
  const modelDir = path.join(root, "public", "models", "nail-texture-seg");
  const reportsDir = path.join(root, "reports");
  await mkdir(modelDir, { recursive: true });
  await mkdir(reportsDir, { recursive: true });

  const manifestPath = await createManifest(modelDir, "nail-texture-seg-v2");
  const pipelineReportPath = path.join(reportsDir, "training-release-pipeline-report.json");
  await writeFile(
    pipelineReportPath,
    JSON.stringify(
      {
        paths: {
          manifestPath,
        },
      },
      null,
      2
    ),
    "utf8"
  );

  const decisionReportPath = path.join(reportsDir, "release-decision-report.json");
  await writeFile(
    decisionReportPath,
    JSON.stringify(
      {
        pipelineReportPath,
        candidateVersion: "nail-texture-seg-v2",
        decision: {
          status: "manual_review",
          summary: "needs human signoff",
          reasons: ["postprocess failures remain"],
          nextActions: ["inspect summary"],
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
      "scripts/promote-approved-release.ts",
      "--decision-report",
      decisionReportPath,
      "--allow-manual-review",
      "true",
    ],
    { cwd: path.resolve(".") }
  );

  const summary = JSON.parse(stdout) as {
    ok: boolean;
    decisionStatus: string;
    registerSummary: { registeredVersion: string };
  };
  assert.equal(summary.ok, true);
  assert.equal(summary.decisionStatus, "manual_review");
  assert.equal(summary.registerSummary.registeredVersion, "nail-texture-seg-v2");
});
