import assert from "node:assert/strict";
import { execFile } from "node:child_process";
import { mkdir, mkdtemp, readFile, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { promisify } from "node:util";
import test from "node:test";

const execFileAsync = promisify(execFile);

async function writeJson(filePath: string, value: unknown) {
  await mkdir(path.dirname(filePath), { recursive: true });
  await writeFile(filePath, JSON.stringify(value, null, 2), "utf8");
}

test("refresh pipeline persists aggregate evidence even when readiness gates fail", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-mvp-refresh-"));
  const datasetRoot = path.join(root, "dataset");
  const manifestPath = path.join(root, "models", "manifest.json");
  const packageJsonPath = path.join(root, "package.json");
  const mvpReportPath = path.join(root, "reports", "mvp.json");
  const outputPath = path.join(root, "reports", "refresh.json");

  await writeJson(manifestPath, {
    version: "nail-texture-seg-v1",
    inputSize: 640,
    task: "segment",
    backendPreferences: ["wasm"],
    modelFile: "missing.onnx",
    labels: ["nail_texture"],
  });
  await writeJson(packageJsonPath, {
    scripts: { test: "test", lint: "lint", build: "build" },
    dependencies: { "onnxruntime-web": "^1.27.0" },
  });

  let caught: unknown;
  try {
    await execFileAsync(
      process.execPath,
      [
        "--no-warnings",
        "--experimental-strip-types",
        "scripts/refresh-nail-texture-mvp-readiness.ts",
        "--dataset-root",
        datasetRoot,
        "--manifest",
        manifestPath,
        "--package-json",
        packageJsonPath,
        "--mvp-report",
        mvpReportPath,
        "--output",
        outputPath,
      ],
      { cwd: path.resolve(".") }
    );
  } catch (error) {
    caught = error;
  }

  assert.ok(caught, "current empty fixture should fail readiness gates");
  const report = JSON.parse(await readFile(outputPath, "utf8")) as {
    ok: boolean;
    steps: Array<{ name: string; ok: boolean }>;
    artifacts: {
      trainingDatasetReadiness: { ok: boolean } | null;
      mvpReadiness: { ok: boolean; checks: Array<{ name: string; ok: boolean }> } | null;
    };
  };
  assert.equal(report.ok, false);
  assert.deepEqual(
    report.steps.map((step) => step.name),
    ["refresh-training-dataset-readiness", "audit-mvp-readiness"]
  );
  assert.equal(report.steps[0]?.ok, false);
  assert.equal(report.steps[1]?.ok, false);
  assert.equal(report.artifacts.trainingDatasetReadiness?.ok, false);
  assert.equal(report.artifacts.mvpReadiness?.ok, false);
  assert.equal(
    report.artifacts.mvpReadiness?.checks.find((check) => check.name === "phase1_dataset")?.ok,
    false
  );
  await readFile(mvpReportPath, "utf8");
});
