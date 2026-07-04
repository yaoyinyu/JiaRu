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

async function createReadyDataset(root: string) {
  const phase1Readiness = {
    ok: true,
    totals: { images: 200, validMasks: 800 },
    splitCounts: { train: 140, val: 30, test: 30 },
    gates: {
      imageCount: { ok: true, actual: 200, required: 200 },
      validMaskCount: { ok: true, actual: 800, required: 800 },
      labelAuditPass: { ok: true, actual: 0, required: 0 },
      testSplitHasNegative: { ok: true, actual: 4, required: 1 },
      testSplitHasComplexBackground: { ok: true, actual: 6, required: 1 },
    },
  };
  await writeJson(path.join(root, "metadata", "phase1-readiness.json"), phase1Readiness);
  await writeJson(path.join(root, "metadata", "training-dataset-readiness-release.json"), {
    ok: true,
    datasetRoot: root,
    authorizationMode: "release",
    artifactPaths: {
      sourceAuthorization: path.join(root, "metadata", "training-source-authorization-release.json"),
      phase1Readiness: path.join(root, "metadata", "phase1-readiness.json"),
    },
    steps: [
      { name: "audit-sources-csv", ok: true },
      { name: "audit-training-source-authorization", ok: true },
      { name: "audit-phase1-readiness", ok: true },
    ],
    artifacts: {
      sourceAuthorization: {
        ok: true,
        mode: "release",
        recordCount: 200,
        issues: [],
      },
      phase1Readiness,
    },
  });
}

async function createManifestWithModel(root: string) {
  const modelDir = path.join(root, "public", "models", "nail-texture-seg");
  await mkdir(modelDir, { recursive: true });
  await writeJson(path.join(modelDir, "manifest.json"), {
    version: "nail-texture-seg-v1",
    inputSize: 640,
    task: "segment",
    backendPreferences: ["webgpu", "wasm"],
    modelFile: "nail-texture-seg-v1.onnx",
        modelSizeBytes: 307200,
        sha256: "7818f5542a0404157573be6cffc0e0c8e68ce3c0f5d17d07ccdd9313fb700baf",
    labels: ["nail_texture"],
  });
  await writeFile(path.join(modelDir, "nail-texture-seg-v1.onnx"), Buffer.alloc(300 * 1024), "binary");
  return path.join(modelDir, "manifest.json");
}

test("audit-nail-texture-mvp-readiness passes when all MVP evidence is present", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-mvp-ready-pass-"));
  const datasetRoot = path.join(root, "model", "datasets", "nail-texture-v1");
  await createReadyDataset(datasetRoot);
  const manifestPath = await createManifestWithModel(root);
  const packageJsonPath = path.join(root, "package.json");
  await writeJson(packageJsonPath, {
    scripts: {
      test: "node --test",
      lint: "eslint",
      build: "next build",
    },
    dependencies: {
      "onnxruntime-web": "^1.27.0",
    },
  });
  const outputPath = path.join(root, "mvp-readiness.json");

  const { stdout } = await execFileAsync(
    process.execPath,
    [
      "--no-warnings",
      "--experimental-strip-types",
      "scripts/audit-nail-texture-mvp-readiness.ts",
      "--dataset-root",
      datasetRoot,
      "--manifest",
      manifestPath,
      "--package-json",
      packageJsonPath,
      "--output",
      outputPath,
    ],
    { cwd: path.resolve(".") }
  );

  const report = JSON.parse(stdout) as {
    ok: boolean;
    summary: { passed: number; failed: number };
    checks: Array<{ name: string; ok: boolean }>;
    nextCommands: string[];
  };
  assert.equal(report.ok, true);
  assert.equal(report.summary.failed, 0);
  assert.equal(report.summary.passed, report.checks.length);
  assert.ok(report.checks.some((check) => check.name === "browser_model_asset" && check.ok));
  assert.deepEqual(report.nextCommands, []);
  const persisted = JSON.parse(await readFile(outputPath, "utf8")) as { ok: boolean };
  assert.equal(persisted.ok, true);
});


test("audit-nail-texture-mvp-readiness rejects placeholder-sized browser model assets", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-mvp-ready-placeholder-"));
  const datasetRoot = path.join(root, "model", "datasets", "nail-texture-v1");
  await createReadyDataset(datasetRoot);
  const manifestPath = await createManifestWithModel(root);
  await writeFile(path.join(path.dirname(manifestPath), "nail-texture-seg-v1.onnx"), Buffer.alloc(1024), "binary");
  const packageJsonPath = path.join(root, "package.json");
  await writeJson(packageJsonPath, {
    scripts: { test: "node --test", lint: "eslint", build: "next build" },
    dependencies: { "onnxruntime-web": "^1.27.0" },
  });

  await assert.rejects(
    execFileAsync(
      process.execPath,
      [
        "--no-warnings",
        "--experimental-strip-types",
        "scripts/audit-nail-texture-mvp-readiness.ts",
        "--dataset-root",
        datasetRoot,
        "--manifest",
        manifestPath,
        "--package-json",
        packageJsonPath,
      ],
      { cwd: path.resolve(".") }
    ),
    (error: Error & { stdout?: string }) => {
      const report = JSON.parse(error.stdout ?? "{}") as {
        ok: boolean;
        checks: Array<{ name: string; ok: boolean; evidence: Record<string, unknown>; nextSteps: string[] }>;
      };
      const modelCheck = report.checks.find((check) => check.name === "browser_model_asset");
      assert.equal(report.ok, false);
      assert.equal(modelCheck?.ok, false);
      assert.equal(modelCheck?.evidence.sizeTier, "placeholder");
      assert.ok(modelCheck?.nextSteps.some((item) => item.includes("placeholder ONNX files below 256KB")));
      return true;
    }
  );
});
test("audit-nail-texture-mvp-readiness reports real dataset and model gaps", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-mvp-ready-fail-"));
  const datasetRoot = path.join(root, "model", "datasets", "nail-texture-v1");
  await writeJson(path.join(datasetRoot, "metadata", "phase1-readiness.json"), {
    ok: false,
    totals: { images: 0, validMasks: 0 },
    splitCounts: { train: 0, val: 0, test: 0 },
    gates: {
      imageCount: { ok: false, actual: 0, required: 200 },
      validMaskCount: { ok: false, actual: 0, required: 800 },
      labelAuditPass: { ok: true, actual: 0, required: 0 },
      testSplitHasNegative: { ok: false, actual: 0, required: 1 },
      testSplitHasComplexBackground: { ok: false, actual: 0, required: 1 },
    },
  });
  const modelDir = path.join(root, "public", "models", "nail-texture-seg");
  await mkdir(modelDir, { recursive: true });
  const manifestPath = path.join(modelDir, "manifest.json");
  await writeJson(manifestPath, {
    version: "nail-texture-seg-v1",
    inputSize: 640,
    task: "segment",
    backendPreferences: ["webgpu", "wasm"],
    modelFile: "missing.onnx",
        modelSizeBytes: 307200,
        sha256: "7818f5542a0404157573be6cffc0e0c8e68ce3c0f5d17d07ccdd9313fb700baf",
    labels: ["nail_texture"],
  });

  let caught: unknown;
  try {
    await execFileAsync(
      process.execPath,
      [
        "--no-warnings",
        "--experimental-strip-types",
        "scripts/audit-nail-texture-mvp-readiness.ts",
        "--dataset-root",
        datasetRoot,
        "--manifest",
        manifestPath,
      ],
      { cwd: path.resolve(".") }
    );
  } catch (error) {
    caught = error;
  }

  assert.ok(caught, "audit should fail until real MVP evidence exists");
  const stdout = (caught as { stdout?: string }).stdout ?? "";
  const report = JSON.parse(stdout) as {
    ok: boolean;
    summary: { failed: number };
    checks: Array<{ name: string; ok: boolean; evidence: Record<string, unknown>; nextSteps: string[] }>;
    nextSteps: string[];
    nextCommands: string[];
  };
  assert.equal(report.ok, false);
  assert.ok(report.summary.failed >= 3);
  assert.equal(report.checks.find((check) => check.name === "phase1_dataset")?.ok, false);
  assert.equal(report.checks.find((check) => check.name === "training_source_authorization")?.ok, false);
  assert.equal(report.checks.find((check) => check.name === "browser_model_asset")?.ok, false);
  assert.match(report.nextSteps.join("\n"), /Train\/export a real ONNX segmentation model/);
  assert.match(report.nextSteps.join("\n"), /200 images and 800 valid nail masks/);
  assert.match(report.nextSteps.join("\n"), /source authorization errors/);
  assert.ok(
    report.nextCommands.some((command) => command.includes("generate-first-batch-checklist.ts"))
  );
  assert.ok(
    report.nextCommands.some((command) =>
      command.includes("verify-training-dataset-readiness.ts")
    )
  );
  assert.ok(
    report.nextCommands.some((command) => command.includes("run-training-release-pipeline.ts"))
  );
  assert.equal(new Set(report.nextCommands).size, report.nextCommands.length);
});
