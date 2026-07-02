import assert from "node:assert/strict";
import { execFile } from "node:child_process";
import { mkdtemp, mkdir, readFile, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { promisify } from "node:util";
import test from "node:test";

const execFileAsync = promisify(execFile);

test("register-release-trace-index creates or updates release-history-manifest with a new trace index", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-register-release-trace-"));
  const reportDir = path.join(root, "reports");
  await mkdir(reportDir, { recursive: true });

  const traceA = path.join(reportDir, "trace-a.json");
  const traceB = path.join(reportDir, "trace-b.json");
  const historyManifestPath = path.join(reportDir, "release-history-manifest.json");

  await writeFile(
    traceA,
    JSON.stringify(
      {
        candidateVersion: "nail-texture-seg-v1",
        currentRegistryVersion: "nail-texture-seg-v1",
        batch: { sourceGroup: "seed-batch-001", datasetRoot: "C:/tmp/dataset", importedFileCount: 2 },
        release: { finalAuditStatus: "pass", derivedAnnotationFailures: 0, postprocessFailures: 0 },
        decision: { status: "approve_candidate", summary: "ok" },
        promotion: { registeredVersion: "nail-texture-seg-v1", currentVersion: "nail-texture-seg-v1" },
      },
      null,
      2
    ),
    "utf8"
  );

  await execFileAsync(
    process.execPath,
    [
      "--no-warnings",
      "--experimental-strip-types",
      "scripts/build-release-history-manifest.ts",
      "--trace-index",
      traceA,
      "--output",
      historyManifestPath,
    ],
    { cwd: path.resolve(".") }
  );

  await writeFile(
    traceB,
    JSON.stringify(
      {
        candidateVersion: "nail-texture-seg-v2",
        currentRegistryVersion: "nail-texture-seg-v2",
        batch: { sourceGroup: "seed-batch-002", datasetRoot: "C:/tmp/dataset", importedFileCount: 3 },
        release: { finalAuditStatus: "pass", derivedAnnotationFailures: 1, postprocessFailures: 1 },
        decision: { status: "manual_review", summary: "review needed" },
        promotion: { registeredVersion: "nail-texture-seg-v2", currentVersion: "nail-texture-seg-v2" },
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
      "scripts/register-release-trace-index.ts",
      "--trace-index",
      traceB,
      "--history-manifest",
      historyManifestPath,
    ],
    { cwd: path.resolve(".") }
  );

  const summary = JSON.parse(stdout) as {
    ok: boolean;
    traceIndexCount: number;
    includedTraceIndexes: string[];
    historyManifestPath: string;
  };
  assert.equal(summary.ok, true);
  assert.equal(summary.traceIndexCount, 2);
  assert.deepEqual(summary.includedTraceIndexes, [traceA, traceB]);

  const saved = JSON.parse(await readFile(summary.historyManifestPath, "utf8")) as {
    totals: { traceIndexes: number };
    entries: Array<{ candidateVersion: string | null }>;
  };
  assert.equal(saved.totals.traceIndexes, 2);
  assert.deepEqual(
    saved.entries.map((entry) => entry.candidateVersion),
    ["nail-texture-seg-v1", "nail-texture-seg-v2"]
  );
});
