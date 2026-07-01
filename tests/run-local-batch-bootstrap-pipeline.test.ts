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
  await cp(path.resolve("model/5188.jpg_wh860.jpg"), path.join(sourceDir, "sample-001.jpg"));
  await cp(path.resolve("model/5188.jpg_wh860.png"), path.join(sourceDir, "sample-002.png"));

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
    ],
    {
      cwd: path.resolve("."),
    }
  );

  const report = JSON.parse(stdout) as {
    ok: boolean;
    reportPath: string;
    steps: Array<{ name: string; ok: boolean; stdout?: { nextStep?: string } }>;
  };
  assert.equal(report.ok, true);
  assert.deepEqual(
    report.steps.map((step) => step.name),
    [
      "bootstrap-seed-batch",
      "run-seed-batch-prep-pipeline",
      "audit-seed-batch-workspace",
    ]
  );
  assert.ok(report.steps.every((step) => step.ok));

  const statusStep = report.steps.find((step) => step.name === "audit-seed-batch-workspace");
  assert.equal(statusStep?.stdout?.nextStep, "manual-annotation-fix-or-import-reviewed-batch");

  const prepReport = JSON.parse(
    await readFile(path.join(batchRoot, "selected", "reviewed-annotation-prep-report.json"), "utf8")
  ) as { preparedCount: number };
  assert.equal(prepReport.preparedCount, 2);

  const saved = JSON.parse(await readFile(report.reportPath, "utf8")) as { ok: boolean };
  assert.equal(saved.ok, true);
});
