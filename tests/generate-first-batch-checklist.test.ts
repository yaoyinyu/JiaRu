import assert from "node:assert/strict";
import { mkdir, mkdtemp, readFile, writeFile } from "node:fs/promises";
import { spawn } from "node:child_process";
import os from "node:os";
import path from "node:path";
import test from "node:test";

test("generate-first-batch-checklist creates actionable commands for an empty dataset", async () => {
  const datasetRoot = await mkdtemp(path.join(os.tmpdir(), "nail-first-batch-checklist-"));
  const metadataDir = path.join(datasetRoot, "metadata");
  await mkdir(metadataDir, { recursive: true });

  const stdout = await new Promise<string>((resolve, reject) => {
    const child = spawn(
      process.execPath,
      [
        "--no-warnings",
        "--experimental-strip-types",
        "model/training/generate-first-batch-checklist.ts",
        "--dataset-root",
        datasetRoot,
        "--source-dir",
        "C:/tmp/local-images",
        "--root-dir",
        "C:/tmp/seed-batch-001",
      ],
      {
        cwd: path.resolve("."),
        stdio: ["ignore", "pipe", "pipe"],
      }
    );
    let out = "";
    let err = "";
    child.stdout.on("data", (chunk) => (out += String(chunk)));
    child.stderr.on("data", (chunk) => (err += String(chunk)));
    child.on("error", reject);
    child.on("exit", (code) => {
      if ((code ?? 0) !== 1) {
        reject(new Error(err || `unexpected exit code: ${code}`));
        return;
      }
      resolve(out);
    });
  });

  const report = JSON.parse(stdout) as {
    firstBatchRecommendation: { targetImages: number };
    steps: Array<{ id: string; command?: string; commands?: string[] }>;
    nextCommands: string[];
  };
  assert.equal(report.firstBatchRecommendation.targetImages, 50);
  assert.ok(report.steps.some((step) => step.id === "bootstrap-seed-batch" && step.command?.includes("bootstrap-seed-batch.ts")));
  assert.ok(report.steps.some((step) => step.id === "recheck-gates" && step.commands?.some((command) => command.includes("plan-phase1-collection.ts"))));
  assert.ok(report.nextCommands.some((command) => command.includes("run-reviewed-batch-import-pipeline.ts")));

  const saved = JSON.parse(
    await readFile(path.join(metadataDir, "first-batch-execution-checklist.json"), "utf8")
  ) as { sourceBatch: { sourceDir: string } };
  assert.equal(saved.sourceBatch.sourceDir, "C:/tmp/local-images");
});

test("generate-first-batch-checklist respects existing collection plan target", async () => {
  const datasetRoot = await mkdtemp(path.join(os.tmpdir(), "nail-first-batch-checklist-plan-"));
  const metadataDir = path.join(datasetRoot, "metadata");
  await mkdir(metadataDir, { recursive: true });
  await writeFile(
    path.join(metadataDir, "phase1-collection-plan.json"),
    JSON.stringify(
      {
        derived: {
          nextBatchTargetImages: 24,
          estimatedBatchesRemaining: 3,
        },
        priorities: [
          {
            id: "add-negative-test-sample",
            status: "pending",
            title: "补负样本",
            target: "下一批至少加入 1 张 negative",
            acceptanceHint: "negative gate should pass",
          },
        ],
      },
      null,
      2
    ),
    "utf8"
  );

  const exitCode = await new Promise<number>((resolve, reject) => {
    const child = spawn(
      process.execPath,
      [
        "--no-warnings",
        "--experimental-strip-types",
        "model/training/generate-first-batch-checklist.ts",
        "--dataset-root",
        datasetRoot,
      ],
      {
        cwd: path.resolve("."),
        stdio: "ignore",
      }
    );
    child.on("error", reject);
    child.on("exit", (code) => resolve(code ?? 0));
  });

  assert.equal(exitCode, 1);
  const saved = JSON.parse(
    await readFile(path.join(metadataDir, "first-batch-execution-checklist.json"), "utf8")
  ) as {
    firstBatchRecommendation: { targetImages: number; estimatedBatchesRemaining: number | null };
    priorities: Array<{ id: string }>;
  };
  assert.equal(saved.firstBatchRecommendation.targetImages, 24);
  assert.equal(saved.firstBatchRecommendation.estimatedBatchesRemaining, 3);
  assert.deepEqual(saved.priorities.map((item) => item.id), ["add-negative-test-sample"]);
});
