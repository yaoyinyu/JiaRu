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
  outputContract?: string;
  resizeMode?: "letterbox";
  scoreThreshold?: number;
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
  | "partial-closeup"
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
  /**
   * 两阶段诊断。stage2 只提供存在性提升分数，
   * promotedProposals 为通过晋级规则的提案数（历史证据下应为 0）。
   */
  stage2?: {
    evaluatedProposals: number;
    promotedProposals: number;
    acceptedByPrimaryRule: number;
    stage2ModelVersion?: string;
  };
  preprocess?: {
    inputSize: number;
    originalWidth: number;
    originalHeight: number;
    scaleX: number;
    scaleY: number;
    resizeScale?: number;
    resizedWidth?: number;
    resizedHeight?: number;
    padLeft?: number;
    padTop?: number;
  };
}

export interface RecognizeNailTexturesOptions {
  preferModel?: boolean;
  manifestUrl?: string;
  maxCandidates?: number;
  workerTimeoutMs?: number;
  includeLowConfidenceCandidates?: boolean;
  debugOutputs?: boolean;
  debugRawModelOutputs?: boolean;
  signal?: AbortSignal;
}

export interface RecognizeNailTextureRequest {
  id: string;
  imageBitmap: ImageBitmap;
  maxCandidates: number;
  workerTimeoutMs?: number;
  includeLowConfidenceCandidates?: boolean;
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

/**
 * 两阶段运行时的第二阶段描述。
 * 契约来源：model/training/candidate57-runtime-selection-lock-v1.json
 * stage2 只提供存在性提升分数，最终 polygon 始终来自 stage1（selectedPolygon=stage1Polygon）。
 */
export interface NailTextureStage2Manifest {
  modelFile: string;
  inputSize: number;
  cropContextRatio: number;
  promotionMarginThreshold: number;
}

export interface NailTextureCompositionManifest {
  proposalThreshold: number;
  acceptanceThreshold: number;
  promotionBandMinimum: number;
  maximumProposalsPerImage: number;
  dedup: {
    maskIouThreshold: number;
    maskContainmentThreshold: number;
    maskScoreTolerance: number;
    boxIouThreshold: number;
  };
}

export interface NailTextureModelManifest {
  /** 未部署时保留计划接口，但禁止加载模型或作为发布资产使用。缺省兼容既有候选。 */
  deploymentStatus?: "deployed" | "not-deployed";
  version: string;
  inputSize: number;
  task: "segment";
  backendPreferences: Array<"webgpu" | "wasm">;
  modelFile: string;
  labels: string[];
  inputLayout?: "NCHW";
  colorOrder?: "RGB";
  normalization?: "zero_to_one";
  resizeMode?: "letterbox";
  outputContract?: string;
  scoreThreshold?: number;
  /** 存在时启用两阶段运行时；缺省则沿用既有单模型路径。 */
  stage2?: NailTextureStage2Manifest;
  /** 两阶段阈值与去重契约；仅在 stage2 存在时生效。 */
  composition?: NailTextureCompositionManifest;
  /**
   * 显式标记该 manifest 不得作为生产身份使用。
   * 仅为 true 时不影响 /models/nail-texture-seg/ 生产 manifest 与 releaseIdentity。
   */
  testOnly?: boolean;
}
