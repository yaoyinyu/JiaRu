import assert from "node:assert/strict";
import test from "node:test";
import {
  choosePreferredModelBackend,
  getSessionIoNames,
  getNailTextureModelRuntime,
  recognizeNailTextures,
  recognizeNailTexturesInWorker,
  resetNailTextureModelRuntimeCache,
  resolveModelUrl,
  resolveOrtExecutionProviders,
  validateNailTextureModelManifest,
} from "../src/lib/nail-texture-recognition/index.ts";

test("model manifest validator rejects unsafe and incompatible manifests", () => {
  assert.deepEqual(
    validateNailTextureModelManifest({
      version: "nail-texture-seg-v1",
      inputSize: 640,
      task: "segment",
      backendPreferences: ["webgpu", "wasm"],
      modelFile: "nail-texture-seg-v1.onnx",
      labels: ["nail_texture"],
    }),
    []
  );

  const errors = validateNailTextureModelManifest({
    version: "",
    inputSize: 0,
    task: "detect",
    backendPreferences: ["webgl"],
    modelFile: "../escape.onnx",
    labels: ["other"],
  });
  assert.ok(errors.includes("manifest_version_required"));
  assert.ok(errors.includes("manifest_task_must_be_segment"));
  assert.ok(errors.includes("manifest_input_size_must_be_positive_integer"));
  assert.ok(errors.includes("manifest_model_file_must_be_safe_onnx_basename"));
  assert.ok(errors.includes("manifest_backend_preferences_invalid"));
  assert.ok(errors.includes("manifest_labels_must_include_nail_texture"));
});

test("recognizeNailTextures falls back when manifest is invalid", async () => {
  resetNailTextureModelRuntimeCache();

  const windowDescriptor = Object.getOwnPropertyDescriptor(globalThis, "window");
  const navigatorDescriptor = Object.getOwnPropertyDescriptor(globalThis, "navigator");
  const originalFetch = globalThis.fetch;

  Object.defineProperty(globalThis, "window", {
    configurable: true,
    writable: true,
    value: { location: { href: "https://example.com/ar-tryon" } },
  });
  Object.defineProperty(globalThis, "navigator", {
    configurable: true,
    writable: true,
    value: {},
  });
  globalThis.fetch = (async () => ({
    ok: true,
    json: async () => ({
      version: "nail-texture-seg-bad",
      inputSize: 640,
      task: "detect",
      backendPreferences: ["wasm"],
      modelFile: "../bad.onnx",
      labels: ["nail_texture"],
    }),
  })) as typeof fetch;

  try {
    const result = await recognizeNailTextures(
      {
        width: 64,
        height: 64,
        data: new Uint8ClampedArray(64 * 64 * 4),
      },
      {
        preferModel: true,
        manifestUrl: "https://example.com/models/nail-texture-seg/bad/manifest.json",
      }
    );

    assert.equal(result.backend, "fallback");
    assert.ok(
      result.warnings.some((warning) =>
        warning.includes("invalid_nail_texture_model_manifest")
      )
    );
  } finally {
    resetNailTextureModelRuntimeCache();
    globalThis.fetch = originalFetch;
    if (windowDescriptor) {
      Object.defineProperty(globalThis, "window", windowDescriptor);
    } else {
      delete (globalThis as typeof globalThis & { window?: unknown }).window;
    }
    if (navigatorDescriptor) {
      Object.defineProperty(globalThis, "navigator", navigatorDescriptor);
    } else {
      delete (globalThis as typeof globalThis & { navigator?: unknown }).navigator;
    }
  }
});
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

test("recognizeNailTextures reports model elapsed time on successful model inference", async () => {
  resetNailTextureModelRuntimeCache();

  const windowDescriptor = Object.getOwnPropertyDescriptor(globalThis, "window");
  const navigatorDescriptor = Object.getOwnPropertyDescriptor(globalThis, "navigator");
  const performanceDescriptor = Object.getOwnPropertyDescriptor(globalThis, "performance");
  const originalFetch = globalThis.fetch;

  const nowValues = [100, 106];

  Object.defineProperty(globalThis, "window", {
    configurable: true,
    writable: true,
    value: {
      location: { href: "https://example.com/ar-tryon" },
      ort: {
        Tensor: class FakeTensor {
          type: string;
          data: Float32Array;
          dims: readonly number[];

          constructor(type: string, data: Float32Array, dims: readonly number[]) {
            this.type = type;
            this.data = data;
            this.dims = dims;
          }
        },
        InferenceSession: {
          create: async () => ({
            inputNames: ["images"],
            run: async () => ({
              output0: {
                dims: [1, 1, 6],
                data: new Float32Array([320, 320, 72, 120, 0.92, 0]),
              },
            }),
          }),
        },
      },
    },
  });
  Object.defineProperty(globalThis, "navigator", {
    configurable: true,
    writable: true,
    value: {},
  });
  Object.defineProperty(globalThis, "performance", {
    configurable: true,
    writable: true,
    value: {
      now: () => nowValues.shift() ?? 106,
    },
  });
  globalThis.fetch = (async () => ({
    ok: true,
    json: async () => ({
      version: "nail-texture-seg-v-success",
      inputSize: 640,
      task: "segment",
      backendPreferences: ["wasm"],
      modelFile: "nail-texture-seg-v-success.onnx",
      labels: ["nail_texture"],
    }),
  })) as typeof fetch;

  try {
    const result = await recognizeNailTextures(
      {
        width: 64,
        height: 64,
        data: new Uint8ClampedArray(64 * 64 * 4).fill(255),
      },
      {
        preferModel: true,
        manifestUrl: "https://example.com/models/nail-texture-seg/v-success/manifest.json",
      }
    );

    assert.equal(result.backend, "model");
    assert.equal(result.modelVersion, "nail-texture-seg-v-success");
    assert.equal(result.elapsedMs, 6);
    assert.equal(result.candidates.length, 1);
  } finally {
    resetNailTextureModelRuntimeCache();
    globalThis.fetch = originalFetch;
    if (windowDescriptor) {
      Object.defineProperty(globalThis, "window", windowDescriptor);
    } else {
      delete (globalThis as typeof globalThis & { window?: unknown }).window;
    }
    if (navigatorDescriptor) {
      Object.defineProperty(globalThis, "navigator", navigatorDescriptor);
    } else {
      delete (globalThis as typeof globalThis & { navigator?: unknown }).navigator;
    }
    if (performanceDescriptor) {
      Object.defineProperty(globalThis, "performance", performanceDescriptor);
    } else {
      delete (globalThis as typeof globalThis & { performance?: unknown }).performance;
    }
  }
});

test("recognizeNailTextures respects maxCandidates on successful model inference", async () => {
  resetNailTextureModelRuntimeCache();

  const windowDescriptor = Object.getOwnPropertyDescriptor(globalThis, "window");
  const navigatorDescriptor = Object.getOwnPropertyDescriptor(globalThis, "navigator");
  const originalFetch = globalThis.fetch;

  Object.defineProperty(globalThis, "window", {
    configurable: true,
    writable: true,
    value: {
      location: { href: "https://example.com/ar-tryon" },
      ort: {
        Tensor: class FakeTensor {
          type: string;
          data: Float32Array;
          dims: readonly number[];

          constructor(type: string, data: Float32Array, dims: readonly number[]) {
            this.type = type;
            this.data = data;
            this.dims = dims;
          }
        },
        InferenceSession: {
          create: async () => ({
            inputNames: ["images"],
            run: async () => ({
              output0: {
                dims: [1, 3, 6],
                data: new Float32Array([
                  120, 120, 60, 100, 0.95, 0,
                  260, 140, 55, 95, 0.85, 0,
                  420, 160, 52, 92, 0.75, 0,
                ]),
              },
            }),
          }),
        },
      },
    },
  });
  Object.defineProperty(globalThis, "navigator", {
    configurable: true,
    writable: true,
    value: {},
  });
  globalThis.fetch = (async () => ({
    ok: true,
    json: async () => ({
      version: "nail-texture-seg-v-capped",
      inputSize: 640,
      task: "segment",
      backendPreferences: ["wasm"],
      modelFile: "nail-texture-seg-v-capped.onnx",
      labels: ["nail_texture"],
    }),
  })) as typeof fetch;

  try {
    const result = await recognizeNailTextures(
      {
        width: 64,
        height: 64,
        data: new Uint8ClampedArray(64 * 64 * 4).fill(255),
      },
      {
        preferModel: true,
        maxCandidates: 2,
        manifestUrl: "https://example.com/models/nail-texture-seg/v-capped/manifest.json",
      }
    );

    assert.equal(result.backend, "model");
    assert.equal(result.candidates.length, 2);
  } finally {
    resetNailTextureModelRuntimeCache();
    globalThis.fetch = originalFetch;
    if (windowDescriptor) {
      Object.defineProperty(globalThis, "window", windowDescriptor);
    } else {
      delete (globalThis as typeof globalThis & { window?: unknown }).window;
    }
    if (navigatorDescriptor) {
      Object.defineProperty(globalThis, "navigator", navigatorDescriptor);
    } else {
      delete (globalThis as typeof globalThis & { navigator?: unknown }).navigator;
    }
  }
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

test("model runtime cache is isolated by manifest url", async () => {
  resetNailTextureModelRuntimeCache();

  const windowDescriptor = Object.getOwnPropertyDescriptor(globalThis, "window");
  const navigatorDescriptor = Object.getOwnPropertyDescriptor(globalThis, "navigator");
  const originalFetch = globalThis.fetch;

  let createCount = 0;
  const fetchCalls: string[] = [];

  Object.defineProperty(globalThis, "window", {
    configurable: true,
    writable: true,
    value: {
      location: { href: "https://example.com/ar-tryon" },
      ort: {
        InferenceSession: {
          create: async (modelUrl: string) => {
            createCount += 1;
            return {
              inputNames: [`images:${modelUrl}`],
              outputNames: [`output:${modelUrl}`],
            };
          },
        },
      },
    },
  });
  Object.defineProperty(globalThis, "navigator", {
    configurable: true,
    writable: true,
    value: {},
  });
  globalThis.fetch = (async (input: string | URL) => {
    const url = String(input);
    fetchCalls.push(url);
    const suffix = url.includes("v2") ? "v2" : "v1";
    return {
      ok: true,
      json: async () => ({
        version: `nail-texture-seg-${suffix}`,
        inputSize: suffix === "v2" ? 512 : 640,
        task: "segment",
        backendPreferences: ["wasm"],
        modelFile: `nail-texture-seg-${suffix}.onnx`,
        labels: ["nail_texture"],
      }),
    } as Response;
  }) as typeof fetch;

  try {
    const runtimeV1 = await getNailTextureModelRuntime(
      "https://example.com/models/nail-texture-seg/v1/manifest.json"
    );
    const runtimeV2 = await getNailTextureModelRuntime(
      "https://example.com/models/nail-texture-seg/v2/manifest.json"
    );
    const runtimeV1Again = await getNailTextureModelRuntime(
      "https://example.com/models/nail-texture-seg/v1/manifest.json"
    );

    assert.equal(runtimeV1.available, true);
    assert.equal(runtimeV2.available, true);
    assert.equal(runtimeV1.info?.version, "nail-texture-seg-v1");
    assert.equal(runtimeV2.info?.version, "nail-texture-seg-v2");
    assert.equal(
      runtimeV1.info?.modelUrl,
      "https://example.com/models/nail-texture-seg/v1/nail-texture-seg-v1.onnx"
    );
    assert.equal(
      runtimeV2.info?.modelUrl,
      "https://example.com/models/nail-texture-seg/v2/nail-texture-seg-v2.onnx"
    );
    assert.strictEqual(runtimeV1Again, runtimeV1);
    assert.deepEqual(fetchCalls, [
      "https://example.com/models/nail-texture-seg/v1/manifest.json",
      "https://example.com/models/nail-texture-seg/v2/manifest.json",
    ]);
    assert.equal(createCount, 2);
  } finally {
    resetNailTextureModelRuntimeCache();
    globalThis.fetch = originalFetch;
    if (windowDescriptor) {
      Object.defineProperty(globalThis, "window", windowDescriptor);
    } else {
      delete (globalThis as typeof globalThis & { window?: unknown }).window;
    }
    if (navigatorDescriptor) {
      Object.defineProperty(globalThis, "navigator", navigatorDescriptor);
    } else {
      delete (globalThis as typeof globalThis & { navigator?: unknown }).navigator;
    }
  }
});
