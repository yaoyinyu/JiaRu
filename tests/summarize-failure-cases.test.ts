import assert from "node:assert/strict";
import { execFile } from "node:child_process";
import { mkdtemp, mkdir, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { promisify } from "node:util";
import test from "node:test";

const execFileAsync = promisify(execFile);

test("summarize-failure-cases aggregates failure classification csv", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-failure-summary-csv-"));
  const reviewDir = path.join(root, "review");
  await mkdir(reviewDir, { recursive: true });
  const csvPath = path.join(reviewDir, "failure-classification.csv");
  await writeFile(
    csvPath,
    [
      "fileName,stage,category,subcategory,severity,action,notes",
      "sample-001.jpg,fallback_overlay,data,strong_reflection,high,add_more_samples,reflection issue",
      "sample-002.jpg,postprocess,postprocess,dirty_mask_crop,medium,tune_thresholds,mask crop issue",
      "sample-003.jpg,ui,ui,confusing_assignment,low,improve_copy,ui issue",
      "",
    ].join("\n"),
    "utf8"
  );

  const { stdout } = await execFileAsync(
    process.execPath,
    [
      "--no-warnings",
      "--experimental-strip-types",
      "scripts/summarize-failure-cases.ts",
      "--failure-csv",
      csvPath,
    ],
    { cwd: path.resolve(".") }
  );

  const summary = JSON.parse(stdout) as {
    totals: { csvRows: number };
    categoryCounts: Record<string, number>;
    csvBreakdown: { severityCounts: Record<string, number> };
    nextSteps: string[];
  };
  assert.equal(summary.totals.csvRows, 3);
  assert.equal(summary.categoryCounts.data, 1);
  assert.equal(summary.categoryCounts.postprocess, 1);
  assert.equal(summary.categoryCounts.ui, 1);
  assert.equal(summary.csvBreakdown.severityCounts.high, 1);
  assert.ok(summary.nextSteps.some((item) => item.includes("优先补数据")));
});

test("summarize-failure-cases can infer a failure category from first-run record", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-failure-summary-record-"));
  const recordPath = path.join(root, "first-run-record.json");
  await writeFile(
    recordPath,
    JSON.stringify(
      {
        model: { artifactOk: true },
        readiness: {
          ok: false,
          fixtureVerified: false,
          imageVerified: true,
          warnings: ["postprocess mask crop is unstable"],
        },
        observations: {
          newWarnings: ["mask crop issue persists"],
        },
        decision: {
          status: "needs_adjustment",
          nextActions: ["fix postprocess"],
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
      "scripts/summarize-failure-cases.ts",
      "--first-run-record",
      recordPath,
    ],
    { cwd: path.resolve(".") }
  );

  const summary = JSON.parse(stdout) as {
    categoryCounts: Record<string, number>;
    inferredFromFirstRunRecord: { category: string; reason: string } | null;
    totals: { inferredRecordFailure: number };
  };
  assert.equal(summary.totals.inferredRecordFailure, 1);
  assert.equal(summary.inferredFromFirstRunRecord?.category, "postprocess");
  assert.equal(summary.categoryCounts.postprocess, 1);
});

test("summarize-failure-cases infers model category from runtime warning prefixes", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-failure-summary-model-warning-"));
  const recordPath = path.join(root, "first-run-record.json");
  await writeFile(
    recordPath,
    JSON.stringify(
      {
        model: { artifactOk: true },
        readiness: {
          ok: false,
          fixtureVerified: true,
          imageVerified: true,
          warnings: ["model_inference_error:simulated_session_run_failure"],
        },
        observations: {
          newWarnings: ["model_outputs_empty_used_fallback"],
        },
        decision: {
          status: "needs_adjustment",
          nextActions: ["review model runtime fallback"],
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
      "scripts/summarize-failure-cases.ts",
      "--first-run-record",
      recordPath,
    ],
    { cwd: path.resolve(".") }
  );

  const summary = JSON.parse(stdout) as {
    categoryCounts: Record<string, number>;
    inferredFromFirstRunRecord: { category: string; reason: string } | null;
    nextSteps: string[];
  };
  assert.equal(summary.inferredFromFirstRunRecord?.category, "model");
  assert.equal(summary.categoryCounts.model, 1);
  assert.ok(summary.inferredFromFirstRunRecord?.reason.includes("model runtime"));
  assert.ok(summary.nextSteps.some((item) => item.includes("妯″瀷")));
});
test("summarize-failure-cases can derive postprocess failures from annotation debug fields", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-failure-summary-annotation-"));
  const annotationDir = path.join(root, "annotations");
  await mkdir(annotationDir, { recursive: true });
  await writeFile(
    path.join(annotationDir, "sample-001.json"),
    JSON.stringify(
      {
        image: { fileName: "sample-001.jpg" },
        annotations: [
          {
            attributes: {
              debug: {
                warnings: ["highlight_hotspots"],
                extractionQualityOk: false,
                extractionQualityWarnings: ["mask_crop_touches_edge"],
                highlightPixels: 10,
                repairedPixels: 7,
                highlightRatio: 0.18,
              },
            },
          },
        ],
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
      "scripts/summarize-failure-cases.ts",
      "--annotation-dir",
      annotationDir,
    ],
    { cwd: path.resolve(".") }
  );

  const summary = JSON.parse(stdout) as {
    totals: { derivedAnnotationFailures: number };
    categoryCounts: Record<string, number>;
    derivedAnnotationBreakdown: { subcategoryCounts: Record<string, number> };
    nextSteps: string[];
  };

  assert.equal(summary.totals.derivedAnnotationFailures, 3);
  assert.equal(summary.categoryCounts.postprocess, 3);
  assert.equal(
    summary.derivedAnnotationBreakdown.subcategoryCounts["postprocess/highlight_hotspots"],
    2
  );
  assert.equal(
    summary.derivedAnnotationBreakdown.subcategoryCounts["postprocess/mask_crop_touches_edge"],
    1
  );
  assert.ok(summary.nextSteps.some((item) => item.includes("优先检查后处理")));
});
