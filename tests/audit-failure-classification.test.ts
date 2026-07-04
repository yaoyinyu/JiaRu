import assert from "node:assert/strict";
import { execFile } from "node:child_process";
import { mkdtemp, readFile, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { promisify } from "node:util";
import test from "node:test";

const execFileAsync = promisify(execFile);
const header = "fileName,stage,category,subcategory,severity,action,notes";

async function runAudit(csvPath: string, extraArgs: string[] = []) {
  return execFileAsync(
    process.execPath,
    [
      "--no-warnings",
      "--experimental-strip-types",
      "scripts/audit-failure-classification.ts",
      "--failure-csv",
      csvPath,
      ...extraArgs,
    ],
    { cwd: path.resolve(".") }
  );
}

test("audit-failure-classification passes for reviewed rows and writes a report", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-failure-audit-pass-"));
  const csvPath = path.join(root, "failure-classification.csv");
  const outputPath = path.join(root, "failure-classification-audit.json");
  await writeFile(
    csvPath,
    [
      header,
      "sample-001.jpg,fallback_overlay,data,strong_reflection,high,add_more_samples,reflection issue",
      "sample-002.jpg,model,model,missed_small_nails,medium,retrain_with_hard_cases,small nails missed",
      "sample-003.jpg,postprocess,postprocess,dirty_mask_crop,medium,tune_thresholds,background leaked into crop",
      "sample-004.jpg,ui,ui,confusing_assignment,low,improve_copy,user assigned wrong finger",
      "",
    ].join("\n"),
    "utf8"
  );

  const { stdout } = await runAudit(csvPath, ["--output", outputPath]);
  const summary = JSON.parse(stdout) as {
    ok: boolean;
    totals: { classifiedRows: number; templateRows: number };
    categoryCounts: Record<string, number>;
    coverage: { hasData: boolean; hasModel: boolean; hasPostprocess: boolean; hasUi: boolean };
    errors: string[];
  };

  assert.equal(summary.ok, true);
  assert.equal(summary.totals.classifiedRows, 4);
  assert.equal(summary.totals.templateRows, 0);
  assert.deepEqual(summary.categoryCounts, { data: 1, model: 1, postprocess: 1, ui: 1 });
  assert.deepEqual(summary.coverage, {
    hasData: true,
    hasModel: true,
    hasPostprocess: true,
    hasUi: true,
  });
  assert.deepEqual(summary.errors, []);

  const persisted = JSON.parse(await readFile(outputPath, "utf8")) as { ok: boolean };
  assert.equal(persisted.ok, true);
});

test("audit-failure-classification fails while template row is still the only evidence", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-failure-audit-template-"));
  const csvPath = path.join(root, "failure-classification.csv");
  await writeFile(
    csvPath,
    [
      header,
      "sample-001.jpg,fallback_overlay,data,strong_reflection,medium,add_more_samples,example row, replace during review",
      "",
    ].join("\n"),
    "utf8"
  );

  await assert.rejects(
    runAudit(csvPath),
    (error: Error & { stdout?: string }) => {
      const summary = JSON.parse(error.stdout ?? "{}") as {
        ok: boolean;
        totals: { classifiedRows: number; templateRows: number };
        errors: string[];
        warnings: string[];
      };
      assert.equal(summary.ok, false);
      assert.equal(summary.totals.classifiedRows, 0);
      assert.equal(summary.totals.templateRows, 1);
      assert.ok(summary.errors.some((item) => item.includes("classified row count 0")));
      assert.ok(summary.warnings.some((item) => item.includes("template example row")));
      return true;
    }
  );
});

test("audit-failure-classification fails invalid enum values and missing required fields", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-failure-audit-invalid-"));
  const csvPath = path.join(root, "failure-classification.csv");
  await writeFile(
    csvPath,
    [
      header,
      "sample-001.jpg,model,other,unknown,bad,do_something,invalid enum values",
      "sample-002.jpg,,data,strong_reflection,high,,missing required fields",
      "",
    ].join("\n"),
    "utf8"
  );

  await assert.rejects(
    runAudit(csvPath),
    (error: Error & { stdout?: string }) => {
      const summary = JSON.parse(error.stdout ?? "{}") as {
        ok: boolean;
        errors: string[];
        totals: { classifiedRows: number };
      };
      assert.equal(summary.ok, false);
      assert.equal(summary.totals.classifiedRows, 2);
      assert.ok(summary.errors.some((item) => item.includes("category must be one of")));
      assert.ok(summary.errors.some((item) => item.includes("severity must be one of")));
      assert.ok(summary.errors.some((item) => item.includes("stage is required")));
      assert.ok(summary.errors.some((item) => item.includes("action is required")));
      return true;
    }
  );
});