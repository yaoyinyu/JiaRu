import assert from "node:assert/strict";
import { execFile } from "node:child_process";
import { mkdtemp, mkdir, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { promisify } from "node:util";
import test from "node:test";

const execFileAsync = promisify(execFile);

test("verify-evaluation-artifacts accepts confusion and prediction visualizations", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-evaluation-artifacts-pass-"));
  const indexPath = path.join(root, "evaluation-artifacts.json");
  await mkdir(path.join(root, "labels"), { recursive: true });
  await Promise.all(
    [
      "confusion_matrix.png",
      "confusion_matrix_normalized.png",
      "PR_curve.png",
      "val_batch0_pred.jpg",
      "labels/sample-001.txt",
      "predictions.json",
    ].map((file) => writeFile(path.join(root, file), "fixture", "utf8"))
  );
  await writeFile(
    indexPath,
    JSON.stringify({
      schema_version: 1,
      split: "test",
      artifacts_dir: root,
      files: [
        "confusion_matrix.png",
        "confusion_matrix_normalized.png",
        "PR_curve.png",
        "val_batch0_pred.jpg",
        "labels/sample-001.txt",
        "predictions.json",
      ],
      counts: { total: 6, plots: 4, prediction_labels: 1, json: 1 },
    }),
    "utf8"
  );

  const { stdout } = await execFileAsync(
    process.execPath,
    [
      "--no-warnings",
      "--experimental-strip-types",
      "scripts/verify-evaluation-artifacts.ts",
      "--index",
      indexPath,
    ],
    { cwd: path.resolve(".") }
  );
  const report = JSON.parse(stdout) as {
    ok: boolean;
    evidence: {
      confusionMatrices: string[];
      predictionVisualizations: string[];
      predictionLabelCount: number;
    };
  };
  assert.equal(report.ok, true);
  assert.equal(report.evidence.confusionMatrices.length, 2);
  assert.equal(report.evidence.predictionVisualizations.length, 1);
  assert.equal(report.evidence.predictionLabelCount, 1);
});

test("verify-evaluation-artifacts rejects missing visual evidence and wrong split", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-evaluation-artifacts-fail-"));
  await mkdir(root, { recursive: true });
  await writeFile(path.join(root, "PR_curve.png"), "fixture", "utf8");
  const indexPath = path.join(root, "evaluation-artifacts.json");
  await writeFile(
    indexPath,
    JSON.stringify({
      schema_version: 1,
      split: "val",
      artifacts_dir: root,
      files: ["PR_curve.png"],
      counts: { total: 1, plots: 1, prediction_labels: 0, json: 0 },
    }),
    "utf8"
  );

  await assert.rejects(
    execFileAsync(
      process.execPath,
      [
        "--no-warnings",
        "--experimental-strip-types",
        "scripts/verify-evaluation-artifacts.ts",
        "--index",
        indexPath,
      ],
      { cwd: path.resolve(".") }
    ),
    (error: unknown) => {
      const execError = error as Error & { stdout?: string };
      const report = JSON.parse(execError.stdout ?? "{}") as {
        ok: boolean;
        errors: string[];
      };
      assert.equal(report.ok, false);
      assert.ok(report.errors.some((item) => item.includes("split must be test")));
      assert.ok(report.errors.some((item) => item.includes("confusion matrix")));
      assert.ok(report.errors.some((item) => item.includes("prediction-versus-ground-truth")));
      return true;
    }
  );
});

test("verify-evaluation-artifacts rejects fabricated, empty, duplicate, and escaping files", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-evaluation-artifacts-integrity-"));
  const indexPath = path.join(root, "evaluation-artifacts.json");
  await writeFile(path.join(root, "confusion_matrix.png"), "", "utf8");
  await writeFile(
    indexPath,
    JSON.stringify({
      schema_version: 1,
      split: "test",
      artifacts_dir: root,
      files: [
        "confusion_matrix.png",
        "confusion_matrix.png",
        "val_batch0_pred.jpg",
        "../outside.png",
      ],
      counts: { total: 99, plots: 99, prediction_labels: 0, json: 0 },
    }),
    "utf8"
  );

  await assert.rejects(
    execFileAsync(
      process.execPath,
      [
        "--no-warnings",
        "--experimental-strip-types",
        "scripts/verify-evaluation-artifacts.ts",
        "--index",
        indexPath,
      ],
      { cwd: path.resolve(".") }
    ),
    (error: unknown) => {
      const execError = error as Error & { stdout?: string };
      const report = JSON.parse(execError.stdout ?? "{}") as {
        ok: boolean;
        errors: string[];
        integrity: {
          unsafePaths: string[];
          duplicatePaths: string[];
          missingOrEmptyFiles: string[];
        };
      };
      assert.equal(report.ok, false);
      assert.deepEqual(report.integrity.unsafePaths, ["../outside.png"]);
      assert.deepEqual(report.integrity.duplicatePaths, ["confusion_matrix.png"]);
      assert.ok(report.integrity.missingOrEmptyFiles.includes("confusion_matrix.png"));
      assert.ok(report.integrity.missingOrEmptyFiles.includes("val_batch0_pred.jpg"));
      assert.ok(report.errors.some((item) => item.includes("artifact count total")));
      return true;
    }
  );
});