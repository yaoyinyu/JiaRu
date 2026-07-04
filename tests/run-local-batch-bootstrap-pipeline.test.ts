import assert from "node:assert/strict";
import { cp, mkdir, mkdtemp, readFile } from "node:fs/promises";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import os from "node:os";
import path from "node:path";
import test from "node:test";

const execFileAsync = promisify(execFile);

test("run-local-batch-bootstrap-pipeline bootstraps a local directory and prepares selected annotations", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-local-bootstrap-pipeline-"));
  const sourceDir = path.join(root, "source");
  const batchRoot = path.join(root, "seed-batch-001");
  await mkdir(sourceDir, { recursive: true });
  await cp(path.resolve("model/5188.jpg_wh860.jpg"), path.join(sourceDir, "5188.jpg_wh860.jpg"));
  await cp(path.resolve("model/5188.jpg_wh860.png"), path.join(sourceDir, "5188.jpg_wh860.png"));

  const { stdout } = await execFileAsync(
    process.execPath,
    [
      "--no-warnings",
      "--experimental-strip-types",
      "model/training/run-local-batch-bootstrap-pipeline.ts",
      "--source-dir",
      sourceDir,
      "--root-dir",
      batchRoot,
      "--source-group",
      "seed-batch-001",
      "--origin-type",
      "web",
      "--default-origin-ref",
      "manual web sourcing 2026-07-01",
      "--fixture-dir",
      path.resolve("model/fixtures"),
    ],
    {
      cwd: path.resolve("."),
    }
  );

  const report = JSON.parse(stdout) as {
    ok: boolean;
    reportPath: string;
    steps: Array<{ name: string; ok: boolean; stdout?: { nextStep?: string; fixtureCount?: number; skippedAnnotationFiles?: string[]; matchedFixtureCount?: number; skippedAnnotationCount?: number } }>;
  };
  assert.equal(report.ok, true);
  assert.deepEqual(
    report.steps.map((step) => step.name),
    [
      "bootstrap-seed-batch",
      "batch-verify-nail-detection",
      "run-seed-batch-prep-pipeline",
      "audit-seed-batch-workspace",
    ]
  );
  assert.ok(report.steps.every((step) => step.ok));

  const bootstrapStep = report.steps.find((step) => step.name === "bootstrap-seed-batch");
  assert.equal(bootstrapStep?.stdout?.fixtureCount, 1);
  assert.deepEqual(bootstrapStep?.stdout?.skippedAnnotationFiles, ["5188.jpg_wh860.png"]);

  const verifyStep = report.steps.find((step) => step.name === "batch-verify-nail-detection");
  assert.equal(verifyStep?.stdout?.matchedFixtureCount, 1);
  assert.equal(verifyStep?.stdout?.skippedAnnotationCount, 0);

  const statusStep = report.steps.find((step) => step.name === "audit-seed-batch-workspace");
  assert.equal(statusStep?.stdout?.nextStep, "manual-annotation-fix-or-import-reviewed-batch");

  const prepReport = JSON.parse(
    await readFile(path.join(batchRoot, "selected", "reviewed-annotation-prep-report.json"), "utf8")
  ) as { preparedCount: number };
  assert.equal(prepReport.preparedCount, 1);

  const saved = JSON.parse(await readFile(report.reportPath, "utf8")) as { ok: boolean };
  assert.equal(saved.ok, true);
});
test("run-local-batch-bootstrap-pipeline stops when overlay precheck fails", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-local-bootstrap-failure-"));
  const sourceDir = path.join(root, "source");
  const batchRoot = path.join(root, "seed-batch-invalid");
  await mkdir(sourceDir, { recursive: true });
  await cp(path.resolve("package.json"), path.join(sourceDir, "invalid.jpg"));

  let stdout = "";
  try {
    await execFileAsync(
      process.execPath,
      [
        "--no-warnings",
        "--experimental-strip-types",
        "model/training/run-local-batch-bootstrap-pipeline.ts",
        "--source-dir",
        sourceDir,
        "--root-dir",
        batchRoot,
        "--source-group",
        "seed-batch-invalid",
        "--origin-type",
        "other",
        "--default-origin-ref",
        "invalid image acceptance",
      ],
      { cwd: path.resolve(".") }
    );
    assert.fail("expected overlay precheck failure");
  } catch (error) {
    stdout = (error as Error & { stdout?: string }).stdout ?? "";
  }

  const report = JSON.parse(stdout) as {
    ok: boolean;
    steps: Array<{ name: string; ok: boolean }>;
  };
  assert.equal(report.ok, false);
  assert.deepEqual(report.steps.map((step) => step.name), [
    "bootstrap-seed-batch",
    "batch-verify-nail-detection",
  ]);
  assert.equal(report.steps[1]?.ok, false);
});
