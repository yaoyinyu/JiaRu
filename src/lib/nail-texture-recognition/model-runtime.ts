import type {
  NailTextureModelBackend,
  NailTextureModelInfo,
  NailTextureModelManifest,
} from "./types.ts";

interface NailTextureModelRuntime {
  available: boolean;
  backend: NailTextureModelBackend;
  info?: NailTextureModelInfo;
  session?: unknown;
  ort?: OrtModuleLike;
  warnings: string[];
}

interface OrtModuleLike {
  env?: {
    wasm?: {
      numThreads?: number;
      proxy?: boolean;
    };
  };
  InferenceSession?: {
    create: (
      modelUrl: string,
      options?: {
        executionProviders?: string[];
        graphOptimizationLevel?: "disabled" | "basic" | "extended" | "layout" | "all";
      }
    ) => Promise<unknown>;
  };
  Tensor?: new (
    type: string,
    data: Float32Array,
    dims: readonly number[]
  ) => unknown;
}

export type NailTextureRuntimeEnvironment = "window" | "worker" | "server";

interface SessionLike {
  inputNames?: string[];
  outputNames?: string[];
}

declare global {
  interface Navigator {
    gpu?: unknown;
  }

  interface Window {
    ort?: unknown;
  }
}

const manifestCache = new Map<string, Promise<NailTextureModelManifest>>();
const runtimeCache = new Map<string, Promise<NailTextureModelRuntime>>();

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isSafeModelFileName(value: string): boolean {
  return (
    value.trim() === value &&
    value.length > 0 &&
    value.toLowerCase().endsWith(".onnx") &&
    !value.includes("/") &&
    !value.includes("\\") &&
    !value.includes(":") &&
    !value.includes("..")
  );
}

export function validateNailTextureModelManifest(manifest: unknown): string[] {
  const errors: string[] = [];
  if (!isPlainObject(manifest)) {
    return ["manifest_must_be_object"];
  }
  if (manifest.deploymentStatus !== undefined &&
      manifest.deploymentStatus !== "deployed" && manifest.deploymentStatus !== "not-deployed") {
    errors.push("manifest_deployment_status_invalid");
  }

  if (typeof manifest.version !== "string" || manifest.version.trim().length === 0) {
    errors.push("manifest_version_required");
  }
  if (manifest.task !== "segment") {
    errors.push("manifest_task_must_be_segment");
  }
  if (!Number.isInteger(manifest.inputSize) || Number(manifest.inputSize) <= 0) {
    errors.push("manifest_input_size_must_be_positive_integer");
  }
  if (typeof manifest.modelFile !== "string" || !isSafeModelFileName(manifest.modelFile)) {
    errors.push("manifest_model_file_must_be_safe_onnx_basename");
  }
  if (!Array.isArray(manifest.backendPreferences) || manifest.backendPreferences.length === 0) {
    errors.push("manifest_backend_preferences_required");
  } else {
    const invalidBackends = manifest.backendPreferences.filter(
      (backend) => backend !== "webgpu" && backend !== "wasm"
    );
    if (invalidBackends.length > 0) {
      errors.push("manifest_backend_preferences_invalid");
    }
  }
  if (!Array.isArray(manifest.labels) || !manifest.labels.includes("nail_texture")) {
    errors.push("manifest_labels_must_include_nail_texture");
  }
  if (manifest.inputLayout != null && manifest.inputLayout !== "NCHW") {
    errors.push("manifest_input_layout_must_be_nchw");
  }
  if (manifest.colorOrder != null && manifest.colorOrder !== "RGB") {
    errors.push("manifest_color_order_must_be_rgb");
  }
  if (manifest.normalization != null && manifest.normalization !== "zero_to_one") {
    errors.push("manifest_normalization_must_be_zero_to_one");
  }
  if (manifest.resizeMode != null && manifest.resizeMode !== "letterbox") {
    errors.push("manifest_resize_mode_must_be_letterbox");
  }
  if (
    manifest.outputContract != null &&
    (typeof manifest.outputContract !== "string" || manifest.outputContract.trim().length === 0)
  ) {
    errors.push("manifest_output_contract_must_be_non_empty_string");
  }
  if (manifest.stage2 != null) {
    if (!isPlainObject(manifest.stage2)) {
      errors.push("manifest_stage2_must_be_object");
    } else {
      const stage2 = manifest.stage2 as Record<string, unknown>;
      const stage2ModelFile = stage2.modelFile;
      const stage2InputSize = stage2.inputSize;
      const stage2CropContextRatio = stage2.cropContextRatio;
      const stage2PromotionMargin = stage2.promotionMarginThreshold;

      if (typeof stage2ModelFile !== "string" || !isSafeModelFileName(stage2ModelFile)) {
        errors.push("manifest_stage2_model_file_must_be_safe_onnx_basename");
      }
      if (typeof stage2InputSize !== "number" || !Number.isInteger(stage2InputSize) || stage2InputSize <= 0) {
        errors.push("manifest_stage2_input_size_must_be_positive_integer");
      }
      if (
        typeof stage2CropContextRatio !== "number" ||
        !Number.isFinite(stage2CropContextRatio) ||
        stage2CropContextRatio < 0
      ) {
        errors.push("manifest_stage2_crop_context_ratio_must_be_non_negative_number");
      }
      if (
        typeof stage2PromotionMargin !== "number" ||
        !Number.isFinite(stage2PromotionMargin)
      ) {
        errors.push("manifest_stage2_promotion_margin_must_be_number");
      }
    }
  }

  if (manifest.testOnly != null && typeof manifest.testOnly !== "boolean") {
    errors.push("manifest_test_only_must_be_boolean");
  }

  if (
    manifest.scoreThreshold != null &&
    (typeof manifest.scoreThreshold !== "number" ||
      !Number.isFinite(manifest.scoreThreshold) ||
      manifest.scoreThreshold <= 0 ||
      manifest.scoreThreshold >= 1)
  ) {
    errors.push("manifest_score_threshold_must_be_between_zero_and_one");
  }

  return errors;
}

function assertValidNailTextureModelManifest(
  manifest: unknown
): asserts manifest is NailTextureModelManifest {
  const errors = validateNailTextureModelManifest(manifest);
  if (errors.length > 0) {
    throw new Error(`invalid_nail_texture_model_manifest:${errors.join(",")}`);
  }
}

export function detectNailTextureRuntimeEnvironment(): NailTextureRuntimeEnvironment {
  const workerGlobal = globalThis as typeof globalThis & {
    window?: unknown;
    location?: { href?: string };
    postMessage?: unknown;
  };
  if (workerGlobal.window) return "window";
  if (
    typeof self !== "undefined" &&
    self === globalThis &&
    typeof workerGlobal.postMessage === "function" &&
    typeof workerGlobal.location?.href === "string"
  ) {
    return "worker";
  }

  return "server";
}

function getRuntimeBaseHref(): string {
  const runtimeGlobal = globalThis as typeof globalThis & {
    window?: { location?: { href?: string } };
    location?: { href?: string };
  };
  return runtimeGlobal.location?.href ?? runtimeGlobal.window?.location?.href ?? "http://localhost";
}

function getInjectedOrtModule(): OrtModuleLike | null {
  const runtimeGlobal = globalThis as typeof globalThis & {
    ort?: unknown;
    window?: { ort?: unknown };
  };
  const injected = runtimeGlobal.ort ?? runtimeGlobal.window?.ort;
  return injected ? (injected as OrtModuleLike) : null;
}

export function choosePreferredModelBackend(
  backendPreferences: Array<"webgpu" | "wasm">,
  environment: {
    hasWebGpu: boolean;
    hasOrt: boolean;
  }
): NailTextureModelBackend {
  if (!environment.hasOrt) return "fallback";
  if (backendPreferences.includes("webgpu") && environment.hasWebGpu) return "webgpu";
  if (backendPreferences.includes("wasm")) return "wasm";
  return "fallback";
}

export function resolveOrtExecutionProviders(
  backend: NailTextureModelBackend
): string[] {
  if (backend === "webgpu") return ["webgpu", "wasm"];
  if (backend === "wasm") return ["wasm"];
  return [];
}

export function resolveModelUrl(
  manifest: NailTextureModelManifest,
  manifestUrl = "/models/nail-texture-seg/manifest.json"
): string {
  assertValidNailTextureModelManifest(manifest);
  if (manifest.deploymentStatus === "not-deployed") throw new Error("model_not_deployed");
  const base = new URL(manifestUrl, getRuntimeBaseHref());
  return new URL(manifest.modelFile, base).toString();
}

async function loadOrtModule(
  backend: Exclude<NailTextureModelBackend, "fallback">
): Promise<OrtModuleLike | null> {
  const injected = getInjectedOrtModule();
  if (injected) return injected;

  try {
    const imported = backend === "webgpu"
      ? await import("onnxruntime-web/webgpu")
      : await import("onnxruntime-web/wasm");
    return imported;
  } catch {
    return null;
  }
}

function getBackendCandidates(
  backendPreferences: Array<"webgpu" | "wasm">,
  hasWebGpu: boolean
): Array<Exclude<NailTextureModelBackend, "fallback">> {
  const candidates: Array<Exclude<NailTextureModelBackend, "fallback">> = [];
  for (const backend of backendPreferences) {
    if (backend === "webgpu" && !hasWebGpu) continue;
    if (!candidates.includes(backend)) candidates.push(backend);
  }
  return candidates;
}

async function createOrtSession(
  ort: OrtModuleLike,
  modelUrl: string,
  backend: NailTextureModelBackend
): Promise<unknown> {
  if (!ort.InferenceSession?.create) {
    throw new Error("onnx_runtime_missing_inference_session");
  }

  if (backend === "wasm" && ort.env?.wasm) {
    ort.env.wasm.proxy = false;
  }

  return await ort.InferenceSession.create(modelUrl, {
    executionProviders: resolveOrtExecutionProviders(backend),
    graphOptimizationLevel: "all",
  });
}

export function getSessionIoNames(session: unknown): {
  inputNames: string[];
  outputNames: string[];
} {
  const typed = session as SessionLike | null;
  return {
    inputNames: typed?.inputNames ? [...typed.inputNames] : [],
    outputNames: typed?.outputNames ? [...typed.outputNames] : [],
  };
}

export async function loadNailTextureModelManifest(
  manifestUrl = "/models/nail-texture-seg/manifest.json"
): Promise<NailTextureModelManifest> {
  const cacheKey = manifestUrl;
  let cached = manifestCache.get(cacheKey);
  if (!cached) {
    cached = (async () => {
      const response = await fetch(manifestUrl, { cache: "force-cache" });
      if (!response.ok) {
        throw new Error(`Failed to load nail texture manifest: ${response.status}`);
      }
      const manifest = await response.json();
      assertValidNailTextureModelManifest(manifest);
      return manifest;
    })();
    manifestCache.set(cacheKey, cached);
  }
  return cached;
}

export async function getNailTextureModelRuntime(
  manifestUrl = "/models/nail-texture-seg/manifest.json"
): Promise<NailTextureModelRuntime> {
  const cacheKey = manifestUrl;
  let cached = runtimeCache.get(cacheKey);
  if (!cached) {
    cached = (async () => {
      const environment = detectNailTextureRuntimeEnvironment();
      if (environment === "server") {
        return {
          available: false,
          backend: "fallback",
          warnings: ["model_runtime_unavailable_on_server"],
        };
      }

      const manifest = await loadNailTextureModelManifest(manifestUrl);
      if (manifest.deploymentStatus === "not-deployed") {
        return { available: false, backend: "fallback", warnings: ["model_not_deployed"] };
      }
      const hasWebGpu = typeof navigator !== "undefined" && typeof navigator.gpu !== "undefined";
      const modelUrl = resolveModelUrl(manifest, manifestUrl);
      const warnings: string[] = [];
      const candidates = getBackendCandidates(manifest.backendPreferences, hasWebGpu);

      for (const backend of candidates) {
        const ort = await loadOrtModule(backend);
        if (!ort) {
          warnings.push(`onnx_runtime_import_failed:${backend}`);
          continue;
        }

        try {
          const session = await createOrtSession(ort, modelUrl, backend);
          const ioNames = getSessionIoNames(session);

          return {
            available: true,
            backend,
            session,
            ort,
            info: {
              version: manifest.version,
              backend,
              inputSize: manifest.inputSize,
              loadedAt: Date.now(),
              modelUrl,
              inputNames: ioNames.inputNames,
              outputNames: ioNames.outputNames,
              outputContract: manifest.outputContract,
              resizeMode: manifest.resizeMode,
              scoreThreshold: manifest.scoreThreshold ?? 0.35,
            },
            warnings,
          };
        } catch (error) {
          warnings.push(
            error instanceof Error
              ? `onnx_session_init_failed:${backend}:${error.message}`
              : `onnx_session_init_failed:${backend}`
          );
        }
      }

      if (candidates.length === 0) {
        return {
          available: false,
          backend: "fallback",
          warnings: ["no_supported_model_backend"],
        };
      }

      return {
        available: false,
        backend: "fallback",
        warnings: warnings.some((warning) => warning.startsWith("onnx_session_init_failed"))
          ? warnings
          : [...warnings, "onnx_runtime_not_loaded"],
      };
    })();
    runtimeCache.set(cacheKey, cached);
  }
  return cached;
}

export function resetNailTextureModelRuntimeCache(): void {
  manifestCache.clear();
  runtimeCache.clear();
  stage2RuntimeCache.clear();
}

export interface NailTextureStage2Runtime {
  available: boolean;
  backend: NailTextureModelBackend;
  session?: unknown;
  ort?: OrtModuleLike;
  warnings: string[];
  modelUrl?: string;
  inputSize: number;
}

const stage2RuntimeCache = new Map<string, Promise<NailTextureStage2Runtime>>();

export function resolveStage2ModelUrl(
  manifest: NailTextureModelManifest,
  manifestUrl = "/models/nail-texture-seg/manifest.json"
): string | null {
  if (!manifest.stage2) return null;
  const base = new URL(manifestUrl, getRuntimeBaseHref());
  return new URL(manifest.stage2.modelFile, base).toString();
}

export async function getNailTextureStage2Runtime(
  manifest: NailTextureModelManifest,
  manifestUrl = "/models/nail-texture-seg/manifest.json"
): Promise<NailTextureStage2Runtime> {
  if (manifest.deploymentStatus === "not-deployed") {
    return { available: false, backend: "fallback", warnings: ["model_not_deployed"], inputSize: 0 };
  }
  const stage2 = manifest.stage2;
  if (!stage2) {
    return {
      available: false,
      backend: "fallback",
      warnings: ["stage2_not_configured"],
      inputSize: 0,
    };
  }

  const cacheKey = `${manifestUrl}::${stage2.modelFile}`;
  let cached = stage2RuntimeCache.get(cacheKey);
  if (!cached) {
    cached = (async (): Promise<NailTextureStage2Runtime> => {
      const environment = detectNailTextureRuntimeEnvironment();
      if (environment === "server") {
        return {
          available: false,
          backend: "fallback",
          warnings: ["model_runtime_unavailable_on_server"],
          inputSize: stage2.inputSize,
        };
      }

      const modelUrl = resolveStage2ModelUrl(manifest, manifestUrl);
      if (!modelUrl) {
        return {
          available: false,
          backend: "fallback",
          warnings: ["stage2_model_url_unresolved"],
          inputSize: stage2.inputSize,
        };
      }

      const hasWebGpu = typeof navigator !== "undefined" && typeof navigator.gpu !== "undefined";
      const warnings: string[] = [];
      const candidates = getBackendCandidates(manifest.backendPreferences, hasWebGpu);

      for (const backend of candidates) {
        const ort = await loadOrtModule(backend);
        if (!ort) {
          warnings.push(`stage2_onnx_runtime_import_failed:${backend}`);
          continue;
        }
        try {
          const session = await createOrtSession(ort, modelUrl, backend);
          return {
            available: true,
            backend,
            session,
            ort,
            warnings,
            modelUrl,
            inputSize: stage2.inputSize,
          };
        } catch (error) {
          warnings.push(
            error instanceof Error
              ? `stage2_onnx_session_init_failed:${backend}:${error.message}`
              : `stage2_onnx_session_init_failed:${backend}`
          );
        }
      }

      return {
        available: false,
        backend: "fallback",
        warnings: [...warnings, "stage2_runtime_unavailable"],
        inputSize: stage2.inputSize,
      };
    })();
    stage2RuntimeCache.set(cacheKey, cached);
  }
  return cached;
}
