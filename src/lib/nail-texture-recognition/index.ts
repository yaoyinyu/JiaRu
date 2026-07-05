export {
  recognizeNailTexturesWithFallback,
} from "./fallback-adapter.ts";
export {
  choosePreferredModelBackend,
  getSessionIoNames,
  getNailTextureModelRuntime,
  loadNailTextureModelManifest,
  resetNailTextureModelRuntimeCache,
  resolveModelUrl,
  resolveOrtExecutionProviders,
  validateNailTextureModelManifest,
} from "./model-runtime.ts";
export {
  serializeModelOutputs,
  summarizeModelOutputs,
} from "./debug.ts";
export type {
  SerializedModelTensor,
} from "./debug.ts";
export {
  buildNailDebugArtifactPaths,
} from "./debug-artifacts.ts";
export {
  validateRealModelFirstRunRecord,
  validateRealModelUiReviewRecord,
} from "./first-run-record.ts";
export type {
  FirstRunRecordValidationResult,
  RealModelFirstRunRecord,
  RealModelUiReviewRecord,
  UiReviewValidationResult,
} from "./first-run-record.ts";
export {
  compareNailDebugPayloads,
} from "./debug-compare.ts";
export type {
  CompareNailDebugOptions,
  NailDetectionDebugMatch,
  NailDetectionDebugPayload,
  NailDetectionDebugRegion,
  NailDetectionGroundTruthRegion,
  NailDebugComparisonPair,
  NailDebugComparisonResult,
} from "./debug-compare.ts";
export {
  assessDebugSamplePriority,
} from "../nail-texture-debug-priority.ts";
export type {
  DebugSamplePriorityAssessment,
  DebugSamplePriorityReason,
  DebugSamplePrioritySummary,
  DebugSamplePriorityTier,
} from "../nail-texture-debug-priority.ts";
export {
  buildFeatheredAlphaMask,
  extractTextureFromMaskDetailed,
  extractTextureFromMask,
  findMaskBounds,
  isSpecularHighlightPixel,
  repairSpecularHighlights,
  summarizeMaskExtractionQuality,
} from "./extract-mask-texture.ts";
export type {
  ExtractedMaskTexture,
  MaskExtractionQualitySummary,
  TextureExtractionDiagnostics,
  TextureHighlightRepairSummary,
} from "./extract-mask-texture.ts";
export {
  inferSuggestedFingers,
} from "./finger-assignment.ts";
export {
  estimateMaskPrincipalAngle,
  postprocessNailTextureDetections,
  stabilizeNailTextureCandidateAngles,
} from "./postprocess.ts";
export {
  preprocessNailTextureImage,
} from "./preprocess.ts";
export {
  assessNailTextureCandidate,
  rankNailTextureCandidates,
} from "./quality.ts";
export {
  disposeNailTextureRecognitionWorker,
  recognizeNailTexturesInWorker,
} from "./client-worker.ts";
export {
  recognizeNailTextures,
} from "./recognize.ts";
export type {
  NailMask,
  NailTextureModelBackend,
  NailTextureModelInfo,
  NailTextureModelManifest,
  NailTextureTensorSummary,
  NailTextureCandidate,
  NailTextureCandidateConfidence,
  NailTextureCandidateSource,
  NailTextureRecognitionResult,
  RecognizeNailTextureRequest,
  RecognizeNailTextureResponse,
  RecognizeNailTexturesOptions,
} from "./types.ts";
