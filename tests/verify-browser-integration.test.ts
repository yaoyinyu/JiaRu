import assert from "node:assert/strict";
import { execFile } from "node:child_process";
import { mkdtemp, mkdir, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { promisify } from "node:util";
import test from "node:test";

const execFileAsync = promisify(execFile);

test("verify-browser-integration passes with healthy artifact and contract files", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-browser-integration-pass-"));
  const modelDir = path.join(root, "model");
  await mkdir(modelDir, { recursive: true });

  const manifestPath = path.join(modelDir, "manifest.json");
  await writeFile(
    manifestPath,
    JSON.stringify(
      {
        version: "nail-texture-seg-v1",
        inputSize: 640,
        task: "segment",
        backendPreferences: ["webgpu", "wasm"],
        modelFile: "nail-texture-seg-v1.onnx",
        labels: ["nail_texture"],
      },
      null,
      2
    ),
    "utf8"
  );
  await writeFile(path.join(modelDir, "nail-texture-seg-v1.onnx"), Buffer.alloc(1024), "binary");

  const pickerPath = path.join(root, "NailArtPicker.tsx");
  const clientWorkerPath = path.join(root, "client-worker.ts");
  const workerPath = path.join(root, "worker.ts");
  const runtimePath = path.join(root, "runtime.ts");

  await writeFile(
    pickerPath,
    `
      const result = await recognizeNailTexturesInWorker({}, { preferModel: true });
      const summary = {
        backend: result.backend,
        modelVersion: result.modelVersion,
        modelBackend: result.modelInfo?.backend,
        elapsedMs: result.elapsedMs,
        warnings: result.warnings
      };
    `,
    "utf8"
  );
  await writeFile(
    clientWorkerPath,
    `
      new Worker("worker.ts");
      const request = { preferModel: options.preferModel ?? true, manifestUrl: options.manifestUrl };
    `,
    "utf8"
  );
  await writeFile(
    workerPath,
    `
      const result = await recognizeNailTextures({}, { manifestUrl: request.manifestUrl });
      const response = { modelInfo: result.modelInfo };
      self.postMessage(response);
    `,
    "utf8"
  );
  await writeFile(
    runtimePath,
    `
      loadNailTextureModelManifest();
      createOrtSession();
      resolveOrtExecutionProviders();
    `,
    "utf8"
  );

  const { stdout } = await execFileAsync(
    process.execPath,
    [
      "--no-warnings",
      "--experimental-strip-types",
      "scripts/verify-browser-integration.ts",
      "--manifest",
      manifestPath,
      "--picker",
      pickerPath,
      "--client-worker",
      clientWorkerPath,
      "--worker",
      workerPath,
      "--runtime",
      runtimePath,
    ],
    { cwd: path.resolve(".") }
  );

  const summary = JSON.parse(stdout) as {
    ok: boolean;
    contractChecks: Array<{ name: string; ok: boolean }>;
    errors: string[];
    warnings: string[];
  };
  assert.equal(summary.ok, true);
  assert.deepEqual(summary.errors, []);
  assert.ok(summary.contractChecks.every((check) => check.ok));
  assert.ok(summary.warnings.some((item) => item.includes("--metrics")));
});

test("verify-browser-integration fails when contract markers are missing", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-browser-integration-fail-"));
  const modelDir = path.join(root, "model");
  await mkdir(modelDir, { recursive: true });

  const manifestPath = path.join(modelDir, "manifest.json");
  await writeFile(
    manifestPath,
    JSON.stringify(
      {
        version: "nail-texture-seg-v1",
        inputSize: 640,
        task: "segment",
        backendPreferences: ["webgpu", "wasm"],
        modelFile: "nail-texture-seg-v1.onnx",
        labels: ["nail_texture"],
      },
      null,
      2
    ),
    "utf8"
  );
  await writeFile(path.join(modelDir, "nail-texture-seg-v1.onnx"), Buffer.alloc(1024), "binary");

  const emptyFile = path.join(root, "empty.ts");
  await writeFile(emptyFile, "export {};\n", "utf8");

  await assert.rejects(
    execFileAsync(
      process.execPath,
      [
        "--no-warnings",
        "--experimental-strip-types",
        "scripts/verify-browser-integration.ts",
        "--manifest",
        manifestPath,
        "--picker",
        emptyFile,
        "--client-worker",
        emptyFile,
        "--worker",
        emptyFile,
        "--runtime",
        emptyFile,
      ],
      { cwd: path.resolve(".") }
    ),
    (error: Error & { stdout?: string }) => {
      const summary = JSON.parse(error.stdout ?? "{}") as {
        ok: boolean;
        errors: string[];
      };
      assert.equal(summary.ok, false);
      assert.ok(summary.errors.some((item) => item.includes("picker_uses_worker_recognition")));
      assert.ok(summary.errors.some((item) => item.includes("runtime_loads_manifest")));
      return true;
    }
  );
});
