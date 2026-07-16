import assert from "node:assert/strict";
import test from "node:test";
import {
  choosePreferredModelBackend,
  detectNailTextureRuntimeEnvironment,
  getSessionIoNames,
  getNailTextureModelRuntime,
  recognizeNailTextures,
  recognizeNailTexturesInWorker,
  resetNailTextureModelRuntimeCache,
  resolveModelUrl,
  resolveOrtExecutionProviders,
  validateNailTextureModelManifest,
} from "../src/lib/nail-texture-recognition/index.ts";

function restoreGlobalProperty(
  name: string,
  descriptor: PropertyDescriptor | undefined
): void {
  if (descriptor) {
    Object.defineProperty(globalThis, name, descriptor);
  } else {
    delete (globalThis as typeof globalThis & Record<string, unknown>)[name];
  }
}

test("model manifest validator rejects unsafe and incompatible manifests", () => {
  assert.deepEqual(
    validateNailTextureModelManifest({
      version: "nail-texture-seg-v1",
      inputSize: 640,
      task: "segment",
      backendPreferences: ["webgpu", "wasm"],
      modelFile: "nail-texture-seg-v1.onnx",
      scoreThreshold: 0.25,
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

  const protocolErrors = validateNailTextureModelManifest({
    version: "nail-texture-seg-v2",
    inputSize: 512,
    task: "segment",
    backendPreferences: ["wasm"],
    modelFile: "nail-texture-seg-v2.onnx",
    labels: ["nail_texture"],
    inputLayout: "NHWC",
    colorOrder: "BGR",
    normalization: "minus_one_to_one",
    resizeMode: "stretch",
    outputContract: "",
    scoreThreshold: 1,
  });
  assert.ok(protocolErrors.includes("manifest_input_layout_must_be_nchw"));
  assert.ok(protocolErrors.includes("manifest_color_order_must_be_rgb"));
  assert.ok(protocolErrors.includes("manifest_normalization_must_be_zero_to_one"));
  assert.ok(protocolErrors.includes("manifest_resize_mode_must_be_letterbox"));
  assert.ok(protocolErrors.includes("manifest_output_contract_must_be_non_empty_string"));
  assert.ok(protocolErrors.includes("manifest_score_threshold_must_be_between_zero_and_one"));
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

test("runtime environment detector recognizes a browser worker without window", () => {
  const descriptors = {
    window: Object.getOwnPropertyDescriptor(globalThis, "window"),
    self: Object.getOwnPropertyDescriptor(globalThis, "self"),
    location: Object.getOwnPropertyDescriptor(globalThis, "location"),
    postMessage: Object.getOwnPropertyDescriptor(globalThis, "postMessage"),
  };

  try {
    delete (globalThis as typeof globalThis & { window?: unknown }).window;
    Object.defineProperty(globalThis, "self", {
      configurable: true,
      value: globalThis,
    });
    Object.defineProperty(globalThis, "location", {
      configurable: true,
      value: { href: "https://example.com/ar-tryon" },
    });
    Object.defineProperty(globalThis, "postMessage", {
      configurable: true,
      value: () => undefined,
    });

    assert.equal(detectNailTextureRuntimeEnvironment(), "worker");
  } finally {
    restoreGlobalProperty("window", descriptors.window);
    restoreGlobalProperty("self", descriptors.self);
    restoreGlobalProperty("location", descriptors.location);
    restoreGlobalProperty("postMessage", descriptors.postMessage);
  }
});

test("model runtime initializes inside a browser worker without window", async () => {
  resetNailTextureModelRuntimeCache();
  const descriptors = {
    window: Object.getOwnPropertyDescriptor(globalThis, "window"),
    self: Object.getOwnPropertyDescriptor(globalThis, "self"),
    location: Object.getOwnPropertyDescriptor(globalThis, "location"),
    postMessage: Object.getOwnPropertyDescriptor(globalThis, "postMessage"),
    navigator: Object.getOwnPropertyDescriptor(globalThis, "navigator"),
    ort: Object.getOwnPropertyDescriptor(globalThis, "ort"),
  };
  const originalFetch = globalThis.fetch;

  try {
    delete (globalThis as typeof globalThis & { window?: unknown }).window;
    Object.defineProperty(globalThis, "self", {
      configurable: true,
      value: globalThis,
    });
    Object.defineProperty(globalThis, "location", {
      configurable: true,
      value: { href: "https://example.com/ar-tryon" },
    });
    Object.defineProperty(globalThis, "postMessage", {
      configurable: true,
      value: () => undefined,
    });
    Object.defineProperty(globalThis, "navigator", {
      configurable: true,
      value: {},
    });
    Object.defineProperty(globalThis, "ort", {
      configurable: true,
      value: {
        InferenceSession: {
          create: async () => ({
            inputNames: ["images"],
            outputNames: ["output0", "proto"],
          }),
        },
      },
    });
    globalThis.fetch = (async () => ({
      ok: true,
      json: async () => ({
        version: "nail-texture-seg-worker",
        inputSize: 512,
        task: "segment",
        backendPreferences: ["wasm"],
        modelFile: "nail-texture-seg-worker.onnx",
        outputContract: "ultralytics-seg-raw-v1",
        resizeMode: "letterbox",
        scoreThreshold: 0.25,
        labels: ["nail_texture"],
      }),
    })) as typeof fetch;

    const runtime = await getNailTextureModelRuntime(
      "/models/nail-texture-seg/manifest.json"
    );

    assert.equal(runtime.available, true);
    assert.equal(runtime.backend, "wasm");
    assert.equal(runtime.info?.version, "nail-texture-seg-worker");
    assert.equal(runtime.info?.outputContract, "ultralytics-seg-raw-v1");
    assert.equal(runtime.info?.resizeMode, "letterbox");
    assert.equal(runtime.info?.scoreThreshold, 0.25);
    assert.equal(
      runtime.info?.modelUrl,
      "https://example.com/models/nail-texture-seg/nail-texture-seg-worker.onnx"
    );
  } finally {
    resetNailTextureModelRuntimeCache();
    globalThis.fetch = originalFetch;
    restoreGlobalProperty("window", descriptors.window);
    restoreGlobalProperty("self", descriptors.self);
    restoreGlobalProperty("location", descriptors.location);
    restoreGlobalProperty("postMessage", descriptors.postMessage);
    restoreGlobalProperty("navigator", descriptors.navigator);
    restoreGlobalProperty("ort", descriptors.ort);
  }
});

test("model runtime retries wasm when webgpu session initialization fails", async () => {
  resetNailTextureModelRuntimeCache();
  const windowDescriptor = Object.getOwnPropertyDescriptor(globalThis, "window");
  const navigatorDescriptor = Object.getOwnPropertyDescriptor(globalThis, "navigator");
  const originalFetch = globalThis.fetch;
  const attemptedProviders: string[][] = [];

  Object.defineProperty(globalThis, "window", {
    configurable: true,
    value: {
      location: { href: "https://example.com/ar-tryon" },
      ort: {
        InferenceSession: {
          create: async (_modelUrl: string, options?: { executionProviders?: string[] }) => {
            const providers = options?.executionProviders ?? [];
            attemptedProviders.push(providers);
            if (providers[0] === "webgpu") {
              throw new Error("simulated_webgpu_failure");
            }
            return { inputNames: ["images"], outputNames: ["output0"] };
          },
        },
      },
    },
  });
  Object.defineProperty(globalThis, "navigator", {
    configurable: true,
    value: { gpu: {} },
  });
  globalThis.fetch = (async () => ({
    ok: true,
    json: async () => ({
      version: "nail-texture-seg-provider-fallback",
      inputSize: 512,
      task: "segment",
      backendPreferences: ["webgpu", "wasm"],
      modelFile: "nail-texture-seg-provider-fallback.onnx",
      labels: ["nail_texture"],
    }),
  })) as typeof fetch;

  try {
    const runtime = await getNailTextureModelRuntime(
      "https://example.com/models/nail-texture-seg/provider-fallback/manifest.json"
    );

    assert.equal(runtime.available, true);
    assert.equal(runtime.backend, "wasm");
    assert.deepEqual(attemptedProviders, [["webgpu", "wasm"], ["wasm"]]);
    assert.ok(
      runtime.warnings.some((warning) =>
        warning.includes("onnx_session_init_failed:webgpu:simulated_webgpu_failure")
      )
    );
  } finally {
    resetNailTextureModelRuntimeCache();
    globalThis.fetch = originalFetch;
    restoreGlobalProperty("window", windowDescriptor);
    restoreGlobalProperty("navigator", navigatorDescriptor);
  }
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
                data: new Float32Array([320, 320, 72, 120, 0.3, 0]),
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
      scoreThreshold: 0.25,
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
    assert.equal(result.modelInfo?.scoreThreshold, 0.25);
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

test("recognizeNailTextures distinguishes model inference failures from manifest failures", async () => {
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
            run: async () => {
              throw new Error("simulated_session_run_failure");
            },
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
      version: "nail-texture-seg-v-run-fails",
      inputSize: 640,
      task: "segment",
      backendPreferences: ["wasm"],
      modelFile: "nail-texture-seg-v-run-fails.onnx",
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
        manifestUrl: "https://example.com/models/nail-texture-seg/v-run-fails/manifest.json",
      }
    );

    assert.equal(result.backend, "fallback");
    assert.ok(
      result.warnings.some((warning) =>
        warning.includes("model_inference_error:simulated_session_run_failure")
      )
    );
    assert.ok(!result.warnings.some((warning) => warning.includes("model_manifest_error")));
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
