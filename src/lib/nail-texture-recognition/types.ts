export interface NailMask {
  width: number;
  height: number;
  data: Uint8Array;
  originX: number;
  originY: number;
  scale: number;
}

export type NailTextureModelBackend = "webgpu" | "wasm" | "fallback";

export interface NailTextureModelInfo {
  version: string;
  backend: NailTextureModelBackend;
  inputSize: number;
  loadedAt: number;
  modelUrl?: string;
  inputNames?: string[];
  outputNames?: string[];
}

export interface NailTextureTensorSummary {
  name: string;
  dims: number[];
  size: number;
  sample: number[];
}

export type NailTextureCandidateConfidence = "high" | "medium" | "low";
export type NailTextureCandidateSource =
  | "model"
  | "mediapipe"
  | "saliency"
  | "manual";

export interface NailTextureCandidate {
  id: string;
  cx: number;
  cy: number;
  length: number;
  width: number;
  angle: number;
  score: number;
  confidence: NailTextureCandidateConfidence;
  source: NailTextureCandidateSource;
  mask?: NailMask;
  warnings?: string[];
  suggestedFinger: number | null;
}

export interface NailTextureRecognitionResult {
  candidates: NailTextureCandidate[];
  backend: "model" | "fallback";
  elapsedMs: number;
  workerElapsedMs?: number;
  modelVersion?: string;
  modelInfo?: NailTextureModelInfo;
  warnings: string[];
  debugOutputs?: NailTextureTensorSummary[];
  rawModelOutputs?: Record<string, { dims?: number[]; data: number[] }>;
  preprocess?: {
    inputSize: number;
    originalWidth: number;
    originalHeight: number;
    scaleX: number;
    scaleY: number;
  };
}

export interface RecognizeNailTexturesOptions {
  preferModel?: boolean;
  manifestUrl?: string;
  maxCandidates?: number;
  debugOutputs?: boolean;
  debugRawModelOutputs?: boolean;
  signal?: AbortSignal;
}

export interface RecognizeNailTextureRequest {
  id: string;
  imageBitmap: ImageBitmap;
  maxCandidates: number;
  preferModel: boolean;
  manifestUrl?: string;
}

export interface RecognizeNailTextureResponse {
  id: string;
  candidates: NailTextureCandidate[];
  backend: "model" | "fallback";
  elapsedMs: number;
  warnings: string[];
  modelVersion?: string;
  modelInfo?: NailTextureModelInfo;
}

export interface NailTextureModelManifest {
  version: string;
  inputSize: number;
  task: "segment";
  backendPreferences: Array<"webgpu" | "wasm">;
  modelFile: string;
  labels: string[];
}
