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
        graphOptimizationLevel?: string;
      }
    ) => Promise<unknown>;
  };
  Tensor?: new (
    type: string,
    data: Float32Array,
    dims: readonly number[]
  ) => unknown;
}

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

function runtimeImport(specifier: string): Promise<unknown> {
  const dynamicImport = new Function(
    "s",
    "return import(s)"
  ) as (s: string) => Promise<unknown>;
  return dynamicImport(specifier);
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
  const base = new URL(manifestUrl, typeof window !== "undefined" ? window.location.href : "http://localhost");
  return new URL(manifest.modelFile, base).toString();
}

async function loadOrtModule(): Promise<OrtModuleLike | null> {
  if (typeof window !== "undefined" && window.ort) {
    return window.ort as OrtModuleLike;
  }

  try {
    const imported = (await runtimeImport("onnxruntime-web")) as OrtModuleLike;
    return imported;
  } catch {
    return null;
  }
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
      return (await response.json()) as NailTextureModelManifest;
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
      if (typeof window === "undefined") {
        return {
          available: false,
          backend: "fallback",
          warnings: ["model_runtime_unavailable_on_server"],
        };
      }

      const manifest = await loadNailTextureModelManifest(manifestUrl);
      const ort = await loadOrtModule();
      const hasOrt = ort != null;
      const hasWebGpu = typeof navigator !== "undefined" && typeof navigator.gpu !== "undefined";
      const backend = choosePreferredModelBackend(manifest.backendPreferences, {
        hasOrt,
        hasWebGpu,
      });

      if (backend === "fallback") {
        return {
          available: false,
          backend,
          warnings: hasOrt ? ["no_supported_model_backend"] : ["onnx_runtime_not_loaded"],
        };
      }

      const modelUrl = resolveModelUrl(manifest, manifestUrl);
      try {
        const session = await createOrtSession(ort as OrtModuleLike, modelUrl, backend);
        const ioNames = getSessionIoNames(session);

        return {
          available: true,
          backend,
          session,
          ort: ort as OrtModuleLike,
          info: {
            version: manifest.version,
            backend,
            inputSize: manifest.inputSize,
            loadedAt: Date.now(),
            modelUrl,
            inputNames: ioNames.inputNames,
            outputNames: ioNames.outputNames,
          },
          warnings: [],
        };
      } catch (error) {
        return {
          available: false,
          backend: "fallback",
          warnings: [
            error instanceof Error
              ? `onnx_session_init_failed:${error.message}`
              : "onnx_session_init_failed",
          ],
        };
      }

    })();
    runtimeCache.set(cacheKey, cached);
  }
  return cached;
}

export function resetNailTextureModelRuntimeCache(): void {
  manifestCache.clear();
  runtimeCache.clear();
}
