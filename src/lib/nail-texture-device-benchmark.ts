export const NAIL_TEXTURE_DEVICE_SESSION_VERSION = "nail-texture-device-session/v1";
export const NAIL_TEXTURE_DEVICE_FAMILIES = ["android", "android-tablet", "iphone", "ipad"] as const;
export type NailTextureDeviceFamily = typeof NAIL_TEXTURE_DEVICE_FAMILIES[number];

export interface NailTextureDeviceBenchmarkSample {
  iteration: number;
  recordedAt: string;
  sessionId: string;
  deviceFamily: NailTextureDeviceFamily;
  elapsedMs: number;
  workerElapsedMs: number | null;
  backend: "model" | "fallback";
  backendName: "webgpu" | "wasm" | "fallback";
  modelVersion: string;
  inputSize: number;
  candidateCount: number;
  warnings: string[];
  usedJSHeapBytes: number | null;
}

export interface NailTextureDeviceBenchmarkEnvironment {
  userAgent: string;
  platform: string;
  hardwareConcurrency: number | null;
  deviceMemoryGiB: number | null;
  viewportWidth: number;
  viewportHeight: number;
  screenWidth: number;
  screenHeight: number;
  devicePixelRatio: number;
}

export function buildNailTextureDeviceSession(options: {
  sessionId: string;
  deviceFamily: NailTextureDeviceFamily;
  image: { name: string; type: string; sizeBytes: number; width: number; height: number; benchmarkWidth: number; benchmarkHeight: number };
  environment: NailTextureDeviceBenchmarkEnvironment;
  samples: NailTextureDeviceBenchmarkSample[];
  warmupRuns: number;
}) {
  const errors: string[] = [];
  const samples = options.samples;
  if (!options.sessionId.trim()) errors.push("sessionId is required");
  if (!NAIL_TEXTURE_DEVICE_FAMILIES.includes(options.deviceFamily)) errors.push("unsupported device family");
  if (samples.length < 20) errors.push(`measured samples ${samples.length} are below 20`);
  if (!Number.isInteger(options.warmupRuns) || options.warmupRuns < 1) errors.push("at least one warmup run is required");
  const sessions = new Set(samples.map((sample) => sample.sessionId));
  const families = new Set(samples.map((sample) => sample.deviceFamily));
  const backends = new Set(samples.map((sample) => sample.backendName));
  const versions = new Set(samples.map((sample) => sample.modelVersion));
  const inputSizes = new Set(samples.map((sample) => sample.inputSize));
  if (sessions.size !== 1 || !sessions.has(options.sessionId)) errors.push("samples must share the declared sessionId");
  if (families.size !== 1 || !families.has(options.deviceFamily)) errors.push("samples must share the declared device family");
  if (backends.size !== 1) errors.push("samples must use one backend");
  if (versions.size !== 1) errors.push("samples must use one model version");
  if (inputSizes.size !== 1) errors.push("samples must use one model input size");
  if (samples.some((sample) => sample.backend !== "model" || sample.backendName === "fallback")) {
    errors.push("fallback recognition is not eligible for device acceptance");
  }
  if (samples.some((sample) => !Number.isFinite(sample.elapsedMs) || sample.elapsedMs <= 0)) {
    errors.push("all elapsed times must be positive finite numbers");
  }
  if (samples.some((sample, index) => sample.iteration !== index + 1)) {
    errors.push("sample iterations must be consecutive and one-based");
  }
  if (samples.some((sample) => !Number.isFinite(Date.parse(sample.recordedAt)))) {
    errors.push("every sample must include a valid recordedAt timestamp");
  }

  const jsHeapSamples = samples.filter((sample) => sample.usedJSHeapBytes !== null).length;
  return {
    version: NAIL_TEXTURE_DEVICE_SESSION_VERSION,
    generatedAt: new Date().toISOString(),
    sessionId: options.sessionId,
    deviceFamily: options.deviceFamily,
    modelVersion: versions.size === 1 ? [...versions][0] : null,
    backend: backends.size === 1 ? [...backends][0] : null,
    inputSize: inputSizes.size === 1 ? [...inputSizes][0] : null,
    warmupRuns: options.warmupRuns,
    measuredRuns: samples.length,
    image: options.image,
    environment: options.environment,
    memoryCapability: {
      jsHeapAvailable: jsHeapSamples === samples.length && samples.length > 0,
      jsHeapSamples,
      processMemoryAvailable: false,
      note: "Browser JavaScript cannot provide trustworthy whole-process mobile memory. Bind Android profiler or iOS Instruments evidence separately.",
    },
    eligibleForPerformanceVerification: errors.length === 0,
    eligibleForMemoryAcceptance: false,
    samples,
    errors,
  };
}
