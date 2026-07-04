import assert from "node:assert/strict";
import { mkdir, mkdtemp, readFile, writeFile } from "node:fs/promises";
import { spawn } from "node:child_process";
import os from "node:os";
import path from "node:path";
import test from "node:test";

test("audit-seed-batch-workspace reports next step for bootstrapped batch", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-seed-status-"));
  await mkdir(path.join(root, "images"), { recursive: true });
  await mkdir(path.join(root, "review"), { recursive: true });
  await writeFile(path.join(root, "images", "sample-001.jpg"), "x");
  await writeFile(
    path.join(root, "seed-batch-001.manifest.json"),
    JSON.stringify(
      {
        version: "nail-texture-intake-batch/v1",
        sourceGroup: "seed-batch-001",
        originType: "web",
        license: "internal-test-only",
        defaultOriginRef: "manual web sourcing 2026-07-01",
        copyImagesToDataset: true,
        items: [{ fileName: "sample-001.jpg" }],
      },
      null,
      2
    ),
    "utf8"
  );

  const stdout = await new Promise<string>((resolve, reject) => {
    const child = spawn(
      process.execPath,
      [
        "--no-warnings",
        "--experimental-strip-types",
        "model/training/audit-seed-batch-workspace.ts",
        "--root-dir",
        root,
      ],
      { cwd: process.cwd(), stdio: ["ignore", "pipe", "pipe"] }
    );
    let out = "";
    let err = "";
    child.stdout.on("data", (chunk) => (out += String(chunk)));
    child.stderr.on("data", (chunk) => (err += String(chunk)));
    child.on("error", reject);
    child.on("exit", (code) => {
      if ((code ?? 0) !== 0) {
        reject(new Error(err || `unexpected exit code: ${code}`));
        return;
      }
      resolve(out);
    });
  });

  const report = JSON.parse(stdout) as {
    stages: { bootstrapped: boolean; annotationsPrepared: boolean };
    nextStep: string;
    suggestedCommands: string[];
    reportPath: string;
  };
  assert.equal(report.stages.bootstrapped, true);
  assert.equal(report.stages.annotationsPrepared, false);
  assert.equal(report.nextStep, "batch-verify-nail-detection");
  assert.ok(report.suggestedCommands[0]?.includes("batch-verify-nail-detection.ts"));
  assert.ok(report.suggestedCommands[0]?.includes("--fixture-dir"));
  assert.ok(report.suggestedCommands[0]?.includes("/fixtures"));

  const persisted = JSON.parse(await readFile(report.reportPath, "utf8")) as {
    nextStep: string;
  };
  assert.equal(persisted.nextStep, "batch-verify-nail-detection");
});

test("audit-seed-batch-workspace reports import step when annotations are prepared", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-seed-status-prepared-"));
  await mkdir(path.join(root, "images"), { recursive: true });
  await mkdir(path.join(root, "review"), { recursive: true });
  await mkdir(path.join(root, "selected", "images"), { recursive: true });
  await mkdir(path.join(root, "selected", "annotations", "raw-json"), { recursive: true });

  await writeFile(path.join(root, "images", "sample-001.jpg"), "x");
  await writeFile(path.join(root, "review", "screening-review.csv"), "header\n");
  await writeFile(path.join(root, "review", "failure-classification.csv"), "header\n");
  await writeFile(path.join(root, "review", "screening-review-audit.json"), JSON.stringify({ ok: true, keptCount: 1 }), "utf8");
  await writeFile(path.join(root, "selected", "reviewed-intake-report.json"), JSON.stringify({ ok: true, copiedCount: 1 }), "utf8");
  await writeFile(path.join(root, "selected", "reviewed-annotation-prep-report.json"), JSON.stringify({ preparedCount: 1, manualFixCount: 1 }), "utf8");
  await writeFile(path.join(root, "selected", "images", "sample-001.jpg"), "x");
  await writeFile(path.join(root, "selected", "annotations", "raw-json", "sample-001.json"), "{}");
  await writeFile(
    path.join(root, "seed-batch-001.manifest.json"),
    JSON.stringify(
      {
        version: "nail-texture-intake-batch/v1",
        sourceGroup: "seed-batch-001",
        originType: "web",
        license: "internal-test-only",
        defaultOriginRef: "manual web sourcing 2026-07-01",
        copyImagesToDataset: true,
        items: [{ fileName: "sample-001.jpg" }],
      },
      null,
      2
    ),
    "utf8"
  );

  const stdout = await new Promise<string>((resolve, reject) => {
    const child = spawn(
      process.execPath,
      [
        "--no-warnings",
        "--experimental-strip-types",
        "model/training/audit-seed-batch-workspace.ts",
        "--root-dir",
        root,
      ],
      { cwd: process.cwd(), stdio: ["ignore", "pipe", "pipe"] }
    );
    let out = "";
    let err = "";
    child.stdout.on("data", (chunk) => (out += String(chunk)));
    child.stderr.on("data", (chunk) => (err += String(chunk)));
    child.on("error", reject);
    child.on("exit", (code) => {
      if ((code ?? 0) !== 0) {
        reject(new Error(err || `unexpected exit code: ${code}`));
        return;
      }
      resolve(out);
    });
  });

  const report = JSON.parse(stdout) as {
    stages: { annotationsPrepared: boolean };
    nextStep: string;
    counts: { selectedAnnotations: number };
    suggestedCommands: string[];
  };
  assert.equal(report.stages.annotationsPrepared, true);
  assert.equal(report.counts.selectedAnnotations, 1);
  assert.equal(report.nextStep, "manual-annotation-fix-or-import-reviewed-batch");
  assert.ok(report.suggestedCommands.some((command) => command.includes("run-reviewed-batch-import-pipeline.ts")));
});
