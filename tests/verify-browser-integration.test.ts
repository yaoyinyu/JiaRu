import assert from "node:assert/strict";
import { execFile } from "node:child_process";
import { mkdtemp, mkdir, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { promisify } from "node:util";
import test from "node:test";

const execFileAsync = promisify(execFile);

/**
 * 2026-10-31 起识别级联（Worker 调用/候选重映射/汇总构造）迁入
 * src/lib/nail-detection-cascade.ts：夹具按「页面组件 + 级联模块」两文件拆分，
 * 契约检查经 --cascade 指向级联夹具。
 */

// 页面侧夹具：只承载仍留在 NailArtPicker 的模式（级联消费、取消链路、输入取景）。
const PICKER_FIXTURE = `
const controller = new AbortController();
      const geometry = calculateDetectionInputGeometry(image.naturalWidth, image.naturalHeight, MAX_DETECTION_DIM);
      ctx.drawImage(image, 0, 0, geometry.width, geometry.height);
      await computeImageDetectedNailRegions(
        imageData,
        image.naturalWidth,
        image.naturalHeight,
        controller.signal
      );
      detectionAbortRef.current?.abort();
      const cancel = <button onClick={cancelDetection}>Cancel</button>;
      const close = <button onClick={closePicker}>Close</button>;
    `;

// 级联侧夹具：承载迁入级联模块的 Worker 调用、候选重映射与汇总构造模式。
const CASCADE_FIXTURE = `
const NAIL_RECOGNITION_WORKER_TIMEOUT_MS = 15000;
const NAIL_TEXTURE_MODEL_MANIFEST_URL = "/models/smoke/manifest.json";
const MAX_DETECTION_DIM = 800;
      const result = await recognizeNailTexturesInWorker({}, { preferModel: true, manifestUrl: NAIL_TEXTURE_MODEL_MANIFEST_URL, workerTimeoutMs: NAIL_RECOGNITION_WORKER_TIMEOUT_MS });
      remapNailTextureCandidatesToOriginal([]);
      const detectionWarnings = [...result.warnings];
      const summary = {
        backend: result.backend,
        modelVersion: result.modelVersion,
        modelBackend: result.modelInfo?.backend,
        elapsedMs: result.elapsedMs,
        workerElapsedMs: result.workerElapsedMs,
        warnings: detectionWarnings
      };
    `;

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
        modelSizeBytes: 307200,
        sha256: "7818f5542a0404157573be6cffc0e0c8e68ce3c0f5d17d07ccdd9313fb700baf",
        labels: ["nail_texture"],
      },
      null,
      2
    ),
    "utf8"
  );
  await writeFile(path.join(modelDir, "nail-texture-seg-v1.onnx"), Buffer.alloc(300 * 1024), "binary");

  const pickerPath = path.join(root, "NailArtPicker.tsx");
  const cascadePath = path.join(root, "nail-detection-cascade.ts");
  const clientWorkerPath = path.join(root, "client-worker.ts");
  const workerPath = path.join(root, "worker.ts");
  const runtimePath = path.join(root, "runtime.ts");
  const packageJsonPath = path.join(root, "package.json");

  await writeFile(pickerPath, PICKER_FIXTURE, "utf8");
  await writeFile(cascadePath, CASCADE_FIXTURE, "utf8");
  await writeFile(
    clientWorkerPath,
    `
      function prepareWorkerImagePixels(source) { return source.data; }
      runtimeGlobal.OffscreenCanvas; worker_unavailable_used_main_thread;
      new Worker("worker.ts");
      const workerTimeoutMs = options.workerTimeoutMs ?? 15000;
      const request = { preferModel: options.preferModel ?? true, manifestUrl: options.manifestUrl, workerTimeoutMs: workerTimeoutMs };
      options.signal.addEventListener("abort", terminateWorkerAndRejectPending);
      worker?.terminate();
      setTimeout(() => {
        workerInstance?.terminate();
        return recognizeNailTextures(source, { preferModel: false }).then((result) => ({
          ...result,
          warnings: [...result.warnings, "worker_timeout_used_main_thread"],
        }));
      }, workerTimeoutMs);
    `,
    "utf8"
  );
  await writeFile(
    workerPath,
    `
      const result = await recognizeNailTextures({}, { manifestUrl: request.manifestUrl, workerTimeoutMs: request.workerTimeoutMs });
      const response = { modelInfo: result.modelInfo };
      request.imageBitmap.close();
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
      function detectNailTextureRuntimeEnvironment() {
        if (self === globalThis) return "worker";
      }
      import("onnxruntime-web/webgpu");
      import("onnxruntime-web/wasm");
      const candidates = getBackendCandidates();
      for (const backend of candidates) {
        const warning = \`onnx_session_init_failed:\${backend}\`;
      }
    `,
    "utf8"
  );
  await writeFile(
    packageJsonPath,
    JSON.stringify({ dependencies: { "onnxruntime-web": "^1.27.0" } }, null, 2),
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
      "--cascade",
      cascadePath,
      "--client-worker",
      clientWorkerPath,
      "--worker",
      workerPath,
      "--runtime",
      runtimePath,
      "--package-json",
      packageJsonPath,
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
  assert.ok(summary.contractChecks.some((check) => check.name === "package_declares_onnxruntime_web"));
  assert.ok(summary.warnings.some((item) => item.includes("--metrics")));
});

test("verify-browser-integration can verify browser contracts without a real model artifact", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-browser-integration-contract-only-"));

  const pickerPath = path.join(root, "NailArtPicker.tsx");
  const cascadePath = path.join(root, "nail-detection-cascade.ts");
  const clientWorkerPath = path.join(root, "client-worker.ts");
  const workerPath = path.join(root, "worker.ts");
  const runtimePath = path.join(root, "runtime.ts");
  const packageJsonPath = path.join(root, "package.json");

  await writeFile(pickerPath, PICKER_FIXTURE, "utf8");
  await writeFile(cascadePath, CASCADE_FIXTURE, "utf8");
  await writeFile(
    clientWorkerPath,
    `
      function prepareWorkerImagePixels(source) { return source.data; }
      runtimeGlobal.OffscreenCanvas; worker_unavailable_used_main_thread;
      new Worker("worker.ts");
      const workerTimeoutMs = options.workerTimeoutMs ?? 15000;
      const request = { preferModel: options.preferModel ?? true, manifestUrl: options.manifestUrl, workerTimeoutMs: workerTimeoutMs };
      options.signal.addEventListener("abort", terminateWorkerAndRejectPending);
      worker?.terminate();
      setTimeout(() => {
        workerInstance?.terminate();
        return recognizeNailTextures(source, { preferModel: false }).then((result) => ({
          ...result,
          warnings: [...result.warnings, "worker_timeout_used_main_thread"],
        }));
      }, workerTimeoutMs);
    `,
    "utf8"
  );
  await writeFile(
    workerPath,
    `
      const result = await recognizeNailTextures({}, { manifestUrl: request.manifestUrl, workerTimeoutMs: request.workerTimeoutMs });
      const response = { modelInfo: result.modelInfo };
      request.imageBitmap.close();
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
      function detectNailTextureRuntimeEnvironment() {
        if (self === globalThis) return "worker";
      }
      import("onnxruntime-web/webgpu");
      import("onnxruntime-web/wasm");
      const candidates = getBackendCandidates();
      for (const backend of candidates) {
        const warning = \`onnx_session_init_failed:\${backend}\`;
      }
    `,
    "utf8"
  );
  await writeFile(
    packageJsonPath,
    JSON.stringify({ dependencies: { "onnxruntime-web": "^1.27.0" } }, null, 2),
    "utf8"
  );

  const { stdout } = await execFileAsync(
    process.execPath,
    [
      "--no-warnings",
      "--experimental-strip-types",
      "scripts/verify-browser-integration.ts",
      "--skip-model-artifact",
      "--picker",
      pickerPath,
      "--cascade",
      cascadePath,
      "--client-worker",
      clientWorkerPath,
      "--worker",
      workerPath,
      "--runtime",
      runtimePath,
      "--package-json",
      packageJsonPath,
    ],
    { cwd: path.resolve(".") }
  );

  const summary = JSON.parse(stdout) as {
    ok: boolean;
    artifact: unknown;
    contractChecks: Array<{ name: string; ok: boolean }>;
    warnings: string[];
  };
  assert.equal(summary.ok, true);
  assert.equal(summary.artifact, null);
  assert.ok(summary.contractChecks.every((check) => check.ok));
  assert.ok(summary.warnings.some((item) => item.includes("--skip-model-artifact")));
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
        modelSizeBytes: 307200,
        sha256: "7818f5542a0404157573be6cffc0e0c8e68ce3c0f5d17d07ccdd9313fb700baf",
        labels: ["nail_texture"],
      },
      null,
      2
    ),
    "utf8"
  );
  await writeFile(path.join(modelDir, "nail-texture-seg-v1.onnx"), Buffer.alloc(300 * 1024), "binary");

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
        "--cascade",
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
      assert.ok(summary.errors.some((item) => item.includes("cascade_uses_worker_recognition")));
      assert.ok(summary.errors.some((item) => item.includes("runtime_loads_manifest")));
      return true;
    }
  );
});

test("verify-browser-integration fails when onnxruntime-web dependency is missing", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-browser-integration-missing-ort-"));
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
        modelSizeBytes: 307200,
        sha256: "7818f5542a0404157573be6cffc0e0c8e68ce3c0f5d17d07ccdd9313fb700baf",
        labels: ["nail_texture"],
      },
      null,
      2
    ),
    "utf8"
  );
  await writeFile(path.join(modelDir, "nail-texture-seg-v1.onnx"), Buffer.alloc(300 * 1024), "binary");

  const pickerPath = path.join(root, "NailArtPicker.tsx");
  const cascadePath = path.join(root, "nail-detection-cascade.ts");
  const clientWorkerPath = path.join(root, "client-worker.ts");
  const workerPath = path.join(root, "worker.ts");
  const runtimePath = path.join(root, "runtime.ts");
  const packageJsonPath = path.join(root, "package.json");

  await writeFile(pickerPath, PICKER_FIXTURE, "utf8");
  await writeFile(cascadePath, CASCADE_FIXTURE, "utf8");
  await writeFile(
    clientWorkerPath,
    `
      function prepareWorkerImagePixels(source) { return source.data; }
      runtimeGlobal.OffscreenCanvas; worker_unavailable_used_main_thread;
      new Worker("worker.ts");
      const workerTimeoutMs = options.workerTimeoutMs ?? 15000;
      const request = { preferModel: options.preferModel ?? true, manifestUrl: options.manifestUrl, workerTimeoutMs: workerTimeoutMs };
      options.signal.addEventListener("abort", terminateWorkerAndRejectPending);
      worker?.terminate();
      setTimeout(() => {
        workerInstance?.terminate();
        return recognizeNailTextures(source, { preferModel: false }).then((result) => ({
          ...result,
          warnings: [...result.warnings, "worker_timeout_used_main_thread"],
        }));
      }, workerTimeoutMs);
    `,
    "utf8"
  );
  await writeFile(
    workerPath,
    `
      const result = await recognizeNailTextures({}, { manifestUrl: request.manifestUrl, workerTimeoutMs: request.workerTimeoutMs });
      const response = { modelInfo: result.modelInfo };
      request.imageBitmap.close();
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
      function detectNailTextureRuntimeEnvironment() {
        if (self === globalThis) return "worker";
      }
      import("onnxruntime-web/webgpu");
      import("onnxruntime-web/wasm");
      const candidates = getBackendCandidates();
      for (const backend of candidates) {
        const warning = \`onnx_session_init_failed:\${backend}\`;
      }
    `,
    "utf8"
  );
  await writeFile(packageJsonPath, JSON.stringify({ dependencies: {} }, null, 2), "utf8");

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
        pickerPath,
        "--cascade",
        cascadePath,
        "--client-worker",
        clientWorkerPath,
        "--worker",
        workerPath,
        "--runtime",
        runtimePath,
        "--package-json",
        packageJsonPath,
      ],
      { cwd: path.resolve(".") }
    ),
    (error: Error & { stdout?: string }) => {
      const summary = JSON.parse(error.stdout ?? "{}") as {
        ok: boolean;
        contractChecks: Array<{ name: string; ok: boolean }>;
        errors: string[];
      };
      assert.equal(summary.ok, false);
      assert.equal(
        summary.contractChecks.find((check) => check.name === "package_declares_onnxruntime_web")?.ok,
        false
      );
      assert.ok(summary.errors.some((item) => item.includes("package_declares_onnxruntime_web")));
      return true;
    }
  );
});
