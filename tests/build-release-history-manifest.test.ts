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
        release: {
          trainingReleasePipelineReportPath: "C:/tmp/v1/training-release-pipeline-report.json",
          finalAuditStatus: "pass",
          derivedAnnotationFailures: 1,
          postprocessFailures: 1,
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
        release: {
          trainingReleasePipelineReportPath: "C:/tmp/v2/training-release-pipeline-report.json",
          finalAuditStatus: "pass",
          derivedAnnotationFailures: 0,
          postprocessFailures: 0,
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
    totals: { traceIndexes: number; uniqueCandidateVersions: number; uniqueSourceGroups: number };
    decisionCounts: Record<string, number>;
    finalAuditStatusCounts: Record<string, number>;
    sourceGroups: string[];
    registeredVersions: string[];
    entries: Array<{ candidateVersion: string | null; sourceGroup: string | null }>;
    outputPath: string;
  };

  assert.equal(summary.totals.traceIndexes, 2);
  assert.equal(summary.totals.uniqueCandidateVersions, 2);
  assert.equal(summary.totals.uniqueSourceGroups, 2);
  assert.equal(summary.decisionCounts.approve_candidate, 1);
  assert.equal(summary.decisionCounts.manual_review, 1);
  assert.equal(summary.finalAuditStatusCounts.pass, 2);
  assert.deepEqual(summary.sourceGroups, ["seed-batch-001", "seed-batch-002"]);
  assert.deepEqual(summary.registeredVersions, ["nail-texture-seg-v1", "nail-texture-seg-v2"]);
  assert.deepEqual(
    summary.entries.map((entry) => entry.candidateVersion),
    ["nail-texture-seg-v1", "nail-texture-seg-v2"]
  );

  const saved = JSON.parse(await readFile(summary.outputPath, "utf8")) as {
    totals: { traceIndexes: number };
  };
  assert.equal(saved.totals.traceIndexes, 2);
});
