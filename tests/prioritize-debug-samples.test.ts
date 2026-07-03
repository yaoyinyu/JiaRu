import assert from "node:assert/strict";
import { execFile } from "node:child_process";
import { mkdtemp, mkdir, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { promisify } from "node:util";
import test from "node:test";

const execFileAsync = promisify(execFile);

async function createSampleDir() {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-prioritize-debug-"));
  const sampleDir = path.join(root, "samples");
  await mkdir(sampleDir, { recursive: true });

  await writeFile(
    path.join(sampleDir, "high-risk.json"),
    JSON.stringify(
      {
        imageId: "local-debug-high",
        imageUrl: "blob:demo",
        image: { width: 320, height: 200 },
        backend: "fallback",
        modelVersion: "fallback-v0",
        modelBackend: "fallback",
        elapsedMs: 0,
        warnings: ["onnx_runtime_not_loaded"],
        originalCandidates: [
          {
            id: "n1",
            cx: 120,
            cy: 80,
            angle: 0.2,
            length: 60,
            width: 26,
            assignedFinger: 1,
            confidence: "high",
            source: "saliency",
            hasMask: true,
            warnings: ["highlight_hotspots"],
          },
        ],
        correctedCandidates: [],
        createdAt: "2026-07-03T00:00:00.000Z",
      },
      null,
      2
    ),
    "utf8"
  );

  await writeFile(
    path.join(sampleDir, "low-risk.json"),
    JSON.stringify(
      {
        imageId: "local-debug-low",
        imageUrl: "blob:demo",
        image: { width: 320, height: 200 },
        backend: "model",
        modelVersion: "nail-texture-seg-v2",
        modelBackend: "wasm",
        elapsedMs: 184,
        warnings: [],
        originalCandidates: [
          {
            id: "n1",
            cx: 100,
            cy: 70,
            angle: 0.1,
            length: 58,
            width: 24,
            assignedFinger: 1,
            confidence: "high",
            source: "model",
            hasMask: true,
            warnings: [],
          },
        ],
        correctedCandidates: [
          {
            id: "n1",
            cx: 101,
            cy: 71,
            angle: 0.1,
            length: 58,
            width: 24,
            assignedFinger: 1,
            confidence: "high",
            source: "model",
            hasMask: true,
            warnings: [],
          },
          {
            id: "n2",
            cx: 180,
            cy: 92,
            angle: 0.2,
            length: 62,
            width: 28,
            assignedFinger: 3,
            confidence: "medium",
            source: "manual",
            hasMask: true,
            warnings: [],
          },
        ],
        createdAt: "2026-07-03T00:00:00.000Z",
      },
      null,
      2
    ),
    "utf8"
  );

  return sampleDir;
}

test("prioritize-debug-samples ranks the highest-value correction samples first", async () => {
  const sampleDir = await createSampleDir();

  const { stdout } = await execFileAsync(
    process.execPath,
    [
      "--no-warnings",
      "--experimental-strip-types",
      "model/training/prioritize-debug-samples.ts",
      "--sample-dir",
      sampleDir,
    ],
    { cwd: path.resolve(".") }
  );

  const report = JSON.parse(stdout) as {
    sampleCount: number;
    totals: { highPriority: number; mediumPriority: number; lowPriority: number };
    backendBreakdown: Record<string, number>;
    modelBackendBreakdown: Record<string, number>;
    correctedCandidateSourceBreakdown: Record<string, number>;
    ranked: Array<{
      imageId: string;
      priorityTier: string;
      priorityScore: number;
      modelBackend?: string;
      elapsedMs: number;
      summary: { manualAddedCandidates: number };
      reasons: Array<{ code: string }>;
    }>;
    reasonBreakdown: Record<string, number>;
  };

  assert.equal(report.sampleCount, 2);
  assert.equal(report.totals.highPriority, 1);
  assert.equal(report.totals.mediumPriority, 1);
  assert.equal(report.totals.lowPriority, 0);
  assert.deepEqual(report.backendBreakdown, { fallback: 1, model: 1 });
  assert.deepEqual(report.modelBackendBreakdown, { fallback: 1, wasm: 1 });
  assert.deepEqual(report.correctedCandidateSourceBreakdown, { manual: 1, model: 1 });
  assert.equal(report.ranked[0]?.imageId, "local-debug-high");
  assert.equal(report.ranked[0]?.priorityTier, "high");
  assert.ok(report.ranked[0]?.reasons.some((item) => item.code === "high_confidence_deleted"));
  assert.equal(report.reasonBreakdown.high_confidence_deleted, 1);
  assert.equal(report.ranked[1]?.modelBackend, "wasm");
  assert.equal(report.ranked[1]?.elapsedMs, 184);
  assert.equal(report.ranked[1]?.summary.manualAddedCandidates, 1);
});

test("prioritize-debug-samples supports top filtering", async () => {
  const sampleDir = await createSampleDir();

  const { stdout } = await execFileAsync(
    process.execPath,
    [
      "--no-warnings",
      "--experimental-strip-types",
      "model/training/prioritize-debug-samples.ts",
      "--sample-dir",
      sampleDir,
      "--top",
      "1",
    ],
    { cwd: path.resolve(".") }
  );

  const report = JSON.parse(stdout) as {
    returnedCount: number;
    ranked: Array<{ imageId: string }>;
  };
  assert.equal(report.returnedCount, 1);
  assert.equal(report.ranked[0]?.imageId, "local-debug-high");
});
