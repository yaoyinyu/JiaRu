export interface NailMask {
  width: number;
  height: number;
  data: Uint8Array;
  originX: number;
  originY: number;
  scale: number;
  /**
   * 可选软边权重（0..255，长度须为 width*height）。
   * 仅本机精细抠图来源提供；未提供时全部既有行为不变。
   * 几何范围仍由二值 `data` 决定，软边只用于收紧边缘 alpha。
   */
  alpha?: Uint8ClampedArray;
  /** 产品层亚像素覆盖率（0..255），与原始二值几何独立保存。 */
  coverageAlpha?: Uint8ClampedArray;
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
/**
 * 候选来源。`cloud-ark`/`cloud-matte` 为云端识别模式（v1.2.216）：
 * 一律辅助定位候选、固定低置信 + `needs_review`，与 `vlm-matte` 兜底同口径，
 * 不计入正式识别成功率（PRODUCT HOLD 不变）。
 */
export type NailTextureCandidateSource =
  | "model"
  | "mediapipe"
  | "partial-closeup"
  | "saliency"
  | "manual"
  | "vlm-matte"
  | "cloud-ark"
  | "cloud-matte";

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
   * radial-refine 模式下 promotedProposals/acceptedByPrimaryRule 为精修产出实例数。
   */
  stage2?: {
    mode?: "rescore" | "radial-refine";
    evaluatedProposals: number;
    promotedProposals: number;
    acceptedByPrimaryRule: number;
    /** radial-refine 模式：presence 拒识丢弃的实例数。 */
    presenceRejected?: number;
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
 *
 * - `mode` 缺省或 `"rescore"`：candidate57 存在性重评分契约（契约来源：
 *   model/training/candidate57-runtime-selection-lock-v1.json）；stage2 只提供
 *   存在性提升分数，最终 polygon 始终来自 stage1（selectedPolygon=stage1Polygon）。
 * - `"radial-refine"`：几何64轮浏览器发布的 mask 替换型精修（原像素径向场 +
 *   radius/presence 双输出 Stage B）；stage1 粗 mask 在 presence 门通过后被
 *   精修 alpha mask 整体替换。
 */
export interface NailTextureStage2Manifest {
  /** 独立产品输出配方；原模型两头与硬mask对拍保持。 */
  edgeRefinement?: { mode: "radial-coverage-v1"; samples: 2 | 4 };
  modelFile: string;
  mode?: "rescore" | "radial-refine";
  /** rescore 模式：Stage B 输入尺寸。 */
  inputSize?: number;
  /** rescore 模式：ROI 上下文比例。 */
  cropContextRatio?: number;
  /** rescore 模式：晋级带宽度。 */
  promotionMarginThreshold?: number;
  /** radial-refine 模式：角度采样数（与服务端 radial_input 一致，默认 2048）。 */
  angularSamples?: number;
  /** radial-refine 模式：presence 拒识阈值（默认 0，presence<阈值 丢弃实例）。 */
  presenceThreshold?: number;
  /** radial-refine 模式：Stage A NMS IoU 阈值（与服务端 0.7 一致）。 */
  nmsIoUThreshold?: number;
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
