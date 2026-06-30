import assert from "node:assert/strict";
import test from "node:test";
import {
  choosePreferredModelBackend,
  getSessionIoNames,
  recognizeNailTextures,
  recognizeNailTexturesInWorker,
  resolveModelUrl,
  resolveOrtExecutionProviders,
} from "../src/lib/nail-texture-recognition/index.ts";

test("model backend chooser prefers webgpu when ort and gpu are available", () => {
  const backend = choosePreferredModelBackend(["webgpu", "wasm"], {
    hasOrt: true,
    hasWebGpu: true,
  });
  assert.equal(backend, "webgpu");
});

test("model backend chooser falls back to wasm without webgpu", () => {
  const backend = choosePreferredModelBackend(["webgpu", "wasm"], {
    hasOrt: true,
    hasWebGpu: false,
  });
  assert.equal(backend, "wasm");
});

test("execution providers follow backend preference", () => {
  assert.deepEqual(resolveOrtExecutionProviders("webgpu"), ["webgpu", "wasm"]);
  assert.deepEqual(resolveOrtExecutionProviders("wasm"), ["wasm"]);
  assert.deepEqual(resolveOrtExecutionProviders("fallback"), []);
});

test("model url resolves relative to manifest location", () => {
  const resolved = resolveModelUrl(
    {
      version: "nail-texture-seg-v1",
      inputSize: 640,
      task: "segment",
      backendPreferences: ["webgpu", "wasm"],
      modelFile: "nail-texture-seg-v1.onnx",
      labels: ["nail_texture"],
    },
    "https://example.com/models/nail-texture-seg/manifest.json"
  );
  assert.equal(
    resolved,
    "https://example.com/models/nail-texture-seg/nail-texture-seg-v1.onnx"
  );
});

test("session io names are extracted when present", () => {
  const io = getSessionIoNames({
    inputNames: ["images"],
    outputNames: ["output0", "proto"],
  });
  assert.deepEqual(io, {
    inputNames: ["images"],
    outputNames: ["output0", "proto"],
  });
});

test("recognizeNailTextures returns fallback result on server runtime", async () => {
  const result = await recognizeNailTextures(
    {
      width: 64,
      height: 64,
      data: new Uint8ClampedArray(64 * 64 * 4),
    },
    {
      preferModel: true,
    }
  );

  assert.equal(result.backend, "fallback");
  assert.ok(result.warnings.some((warning) => warning.includes("model_runtime_unavailable_on_server")));
});

test("recognizeNailTexturesInWorker falls back to main thread outside browser", async () => {
  const result = await recognizeNailTexturesInWorker(
    {
      width: 64,
      height: 64,
      data: new Uint8ClampedArray(64 * 64 * 4),
    },
    {
      preferModel: true,
    }
  );

  assert.equal(result.backend, "fallback");
  assert.ok(result.warnings.some((warning) => warning.includes("worker_unavailable_used_main_thread")));
});
