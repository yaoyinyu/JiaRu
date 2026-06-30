import assert from "node:assert/strict";
import { execFile } from "node:child_process";
import { mkdtemp, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { promisify } from "node:util";
import test from "node:test";
import {
  compareNailDebugPayloads,
  type NailDetectionDebugPayload,
} from "../src/lib/nail-texture-recognition/index.ts";

const execFileAsync = promisify(execFile);

function buildPayload(
  overrides: Partial<NailDetectionDebugPayload> = {}
): NailDetectionDebugPayload {
  return {
    input: "input.jpg",
    annotation: null,
    output: "debug.png",
    candidateMaskOutput: "candidate-mask.png",
    skinMaskOutput: "skin-mask.png",
    debugJsonOutput: "debug.json",
    width: 860,
    height: 573,
    count: 2,
    backend: "fallback",
    warnings: [],
    regions: [
      {
        cx: 100,
        cy: 120,
        angle: 0,
        length: 80,
        width: 40,
        confidence: "high",
        score: 0.8,
      },
      {
        cx: 240,
        cy: 150,
        angle: 0.1,
        length: 90,
        width: 45,
        confidence: "high",
        score: 0.9,
      },
    ],
    groundTruth: null,
    matches: [],
    maxCenterError: 10,
    ...overrides,
  };
}

test("compareNailDebugPayloads matches left-to-right candidates and computes deltas", () => {
  const baseline = buildPayload();
  const candidate = buildPayload({
    backend: "model",
    modelVersion: "nail-texture-seg-v1",
    regions: [
      {
        cx: 102,
        cy: 119,
        angle: 0.05,
        length: 82,
        width: 39,
        confidence: "high",
        score: 0.82,
      },
      {
        cx: 246,
        cy: 155,
        angle: 0.2,
        length: 88,
        width: 47,
        confidence: "high",
        score: 0.95,
      },
    ],
    maxCenterError: 8,
  });

  const comparison = compareNailDebugPayloads(baseline, candidate);
  assert.equal(comparison.ok, true);
  assert.equal(comparison.matchedCount, 2);
  assert.equal(comparison.countDelta, 0);
  assert.equal(comparison.warningDiff.added.length, 0);
  assert.equal(comparison.pairs.length, 2);
  assert.ok(comparison.maxCenterDistance > 0);
  assert.equal(comparison.maxCenterErrorDelta, -2);
});

test("compareNailDebugPayloads reports regressions for dropped candidates and new warnings", () => {
  const baseline = buildPayload();
  const candidate = buildPayload({
    count: 1,
    warnings: ["onnx_session_init_failed"],
    regions: [
      {
        cx: 150,
        cy: 150,
        angle: 0,
        length: 80,
        width: 40,
        confidence: "high",
        score: 0.4,
      },
    ],
  });

  const comparison = compareNailDebugPayloads(baseline, candidate, {
    maxCenterDistance: 20,
  });
  assert.equal(comparison.ok, false);
  assert.ok(comparison.regressionReasons.some((item) => item.startsWith("candidate_count_decreased")));
  assert.ok(comparison.regressionReasons.some((item) => item.startsWith("new_warnings")));
  assert.ok(comparison.regressionReasons.some((item) => item.startsWith("unmatched_baseline")));
});

test("compare-nail-debug script prints JSON summary", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-debug-compare-"));
  const baselinePath = path.join(root, "baseline.json");
  const candidatePath = path.join(root, "candidate.json");
  await writeFile(baselinePath, JSON.stringify(buildPayload(), null, 2), "utf8");
  await writeFile(
    candidatePath,
    JSON.stringify(
      buildPayload({
        backend: "model",
        modelVersion: "nail-texture-seg-v1",
      }),
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
      "scripts/compare-nail-debug.ts",
      baselinePath,
      candidatePath,
    ],
    {
      cwd: path.resolve("."),
    }
  );

  const summary = JSON.parse(stdout) as {
    ok: boolean;
    baselinePath: string;
    candidatePath: string;
    matchedCount: number;
  };
  assert.equal(summary.ok, true);
  assert.equal(summary.baselinePath, baselinePath);
  assert.equal(summary.candidatePath, candidatePath);
  assert.equal(summary.matchedCount, 2);
});
