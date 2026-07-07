import assert from "node:assert/strict";
import { execFile } from "node:child_process";
import { mkdtemp, mkdir, readFile, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { promisify } from "node:util";
import test from "node:test";

const execFileAsync = promisify(execFile);

async function writeTimingSample(
  dirPath: string,
  fileName: string,
  elapsedMs: number,
  backend: "model" | "fallback" = "model",
  workerElapsedMs?: number
) {
  const filePath = path.join(dirPath, fileName);
  await writeFile(
    filePath,
    JSON.stringify(
      {
        imageId: fileName.replace(/\.json$/, ""),
        backend,
        modelVersion: backend === "model" ? "nail-texture-seg-v1" : "fallback-v0",
        elapsedMs,
        workerElapsedMs,
      },
      null,
      2
    ),
    "utf8"
  );
  return filePath;
}

function runPerformance(args: string[]) {
  return execFileAsync(
    process.execPath,
    ["--no-warnings", "--experimental-strip-types", "scripts/verify-recognition-performance.ts", ...args],
    { cwd: path.resolve(".") }
  );
}

test("verify-recognition-performance passes desktop budget and persists report", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-perf-pass-"));
  const sampleA = await writeTimingSample(root, "sample-a.json", 320, "model", 250);
  const sampleB = await writeTimingSample(root, "sample-b.json", 640, "model", 500);
  const outputPath = path.join(root, "performance-report.json");

  const { stdout } = await runPerformance([sampleA, sampleB, "--output", outputPath]);
  const summary = JSON.parse(stdout) as {
    ok: boolean;
    profile: string;
    totals: { samples: number; slowSamples: number };
    stats: {
      averageMs: number;
      p95Ms: number;
      maxMs: number;
      averageWorkerMs: number;
      p95WorkerMs: number;
      averageClientOverheadMs: number;
      p95ClientOverheadMs: number;
    };
  };

  assert.equal(summary.ok, true);
  assert.equal(summary.profile, "desktop");
  assert.equal(summary.totals.samples, 2);
  assert.equal(summary.totals.slowSamples, 0);
  assert.equal(summary.stats.averageMs, 480);
  assert.equal(summary.stats.p95Ms, 640);
  assert.equal(summary.stats.maxMs, 640);
  assert.equal(summary.stats.averageWorkerMs, 375);
  assert.equal(summary.stats.p95WorkerMs, 500);
  assert.equal(summary.stats.averageClientOverheadMs, 105);
  assert.equal(summary.stats.p95ClientOverheadMs, 140);

  const persisted = JSON.parse(await readFile(outputPath, "utf8")) as { ok: boolean };
  assert.equal(persisted.ok, true);
});

test("verify-recognition-performance supports mobile profile sample dirs and skipped json", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-perf-mobile-"));
  const sampleDir = path.join(root, "samples");
  await mkdir(sampleDir, { recursive: true });
  await writeTimingSample(sampleDir, "mobile-a.json", 1200);
  await writeTimingSample(sampleDir, "mobile-b.json", 1499);
  await writeFile(path.join(sampleDir, "metadata.json"), JSON.stringify({ note: "no timing" }), "utf8");

  const { stdout } = await runPerformance(["--profile", "mobile", "--sample-dir", sampleDir, "--min-samples", "2"]);
  const summary = JSON.parse(stdout) as {
    ok: boolean;
    profile: string;
    totals: { inputFiles: number; samples: number; skippedFiles: number; slowSamples: number };
    warnings: string[];
  };

  assert.equal(summary.ok, true);
  assert.equal(summary.profile, "mobile");
  assert.equal(summary.totals.inputFiles, 3);
  assert.equal(summary.totals.samples, 2);
  assert.equal(summary.totals.skippedFiles, 1);
  assert.equal(summary.totals.slowSamples, 0);
  assert.ok(summary.warnings.some((item) => item.includes("elapsedMs")));
  assert.ok(summary.warnings.some((item) => item.includes("workerElapsedMs")));
});

test("verify-recognition-performance fails when samples exceed budget", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-perf-fail-"));
  const sample = await writeTimingSample(root, "slow.json", 901);

  await assert.rejects(
    runPerformance([sample]),
    (error: Error & { stdout?: string }) => {
      const summary = JSON.parse(error.stdout ?? "{}") as {
        ok: boolean;
        totals: { slowSamples: number };
        slowSamples: Array<{ elapsedMs: number }>;
        errors: string[];
      };
      assert.equal(summary.ok, false);
      assert.equal(summary.totals.slowSamples, 1);
      assert.equal(summary.slowSamples[0]?.elapsedMs, 901);
      assert.ok(summary.errors.some((item) => item.includes("desktop budget 800ms")));
      return true;
    }
  );
});
test("verify-recognition-performance can fail on excessive client overhead", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-perf-overhead-"));
  const sample = await writeTimingSample(root, "slow-overhead.json", 700, "model", 420);

  await assert.rejects(
    runPerformance([sample, "--max-client-overhead-ms", "120"]),
    (error: Error & { stdout?: string }) => {
      const summary = JSON.parse(error.stdout ?? "{}") as {
        ok: boolean;
        thresholds: { maxClientOverheadMs: number };
        totals: { slowSamples: number; slowClientOverheadSamples: number };
        slowClientOverheadSamples: Array<{ elapsedMs: number; workerElapsedMs: number; clientOverheadMs: number }>;
        errors: string[];
      };
      assert.equal(summary.ok, false);
      assert.equal(summary.thresholds.maxClientOverheadMs, 120);
      assert.equal(summary.totals.slowSamples, 0);
      assert.equal(summary.totals.slowClientOverheadSamples, 1);
      assert.equal(summary.slowClientOverheadSamples[0]?.elapsedMs, 700);
      assert.equal(summary.slowClientOverheadSamples[0]?.workerElapsedMs, 420);
      assert.equal(summary.slowClientOverheadSamples[0]?.clientOverheadMs, 280);
      assert.ok(summary.errors.some((item) => item.includes("client overhead budget 120ms")));
      return true;
    }
  );
});