export {
  recognizeNailTexturesWithFallback,
} from "./fallback-adapter.ts";
export {
  choosePreferredModelBackend,
  detectNailTextureRuntimeEnvironment,
  getSessionIoNames,
  getNailTextureModelRuntime,
  getNailTextureStage2Runtime,
  loadNailTextureModelManifest,
  resetNailTextureModelRuntimeCache,
  resolveModelUrl,
  resolveOrtExecutionProviders,
  resolveStage2ModelUrl,
  validateNailTextureModelManifest,
} from "./model-runtime.ts";
export type {
  NailTextureRuntimeEnvironment,
  NailTextureStage2Runtime,
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
  buildNailRecognitionMaskOverlay,
} from "./debug-artifacts.ts";
export type {
  NailRecognitionMaskOverlayResult,
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
  inspectSpecularHighlights,
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
  readDetectionRows,
  stabilizeNailTextureCandidateAngles,
} from "./postprocess.ts";
export type { NailTextureDetectionRow } from "./postprocess.ts";
export {
  preprocessNailTextureImage,
} from "./preprocess.ts";
export {
  assessNailTextureCandidate,
  rankNailTextureCandidates,
} from "./quality.ts";
export {
  boxIou,
  candidateBounds,
  instanceCenterInsideCandidate,
  matchMasksByIou,
  matchMasksToCandidates,
  rotatedRectBounds,
} from "./mask-matching.ts";
export type {
  Box,
  MaskMatch,
  MaskMatchResult,
  MatteMatch,
  MatteMatchOptions,
  MatteMatchResult,
  MatchCandidate,
  MatchInstance,
} from "./mask-matching.ts";
export {
  MATTE_ALPHA_MAX_EDGE,
  MATTE_ALPHA_THRESHOLD,
  MATTE_IMAGE_MAX_EDGE,
  alphaGridFromRgba,
  candidateFromMatteInstance,
  computeScaleToMaxEdge,
  decodeAlphaPngToGrid,
  detectNailsWithMatte,
  downsampleAlphaGrid,
  encodeImageForMatte,
  fetchNailMatteAvailability,
  nailMaskFromAlphaGrid,
  refineCandidateMasksWithMatte,
  requestNailMatteFromBrowser,
} from "./vlm-refinement.ts";
export type {
  AlphaGrid,
  MatteDetectOutcome,
  MatteRefinementOutcome,
  NailMatteAvailability,
  NailMatteOutcome,
} from "./vlm-refinement.ts";
export {
  disposeNailTextureRecognitionWorker,
  isWorkerRecognitionSupported,
  recognizeNailTexturesInWorker,
} from "./client-worker.ts";
export {
  recognizeNailTextures,
} from "./recognize.ts";
export {
  CANDIDATE57_COMPOSITION,
  cropProposalRoi,
  runTwoStageComposition,
} from "./two-stage.ts";
export type {
  Stage2ProposalEvaluation,
  TwoStageCompositionDefaults,
  TwoStageRunResult,
} from "./two-stage.ts";
export type {
  NailMask,
  NailTextureModelBackend,
  NailTextureModelInfo,
  NailTextureModelManifest,
  NailTextureCompositionManifest,
  NailTextureStage2Manifest,
  NailTextureTensorSummary,
  NailTextureCandidate,
  NailTextureCandidateConfidence,
  NailTextureCandidateSource,
  NailTextureRecognitionResult,
  RecognizeNailTextureRequest,
  RecognizeNailTextureResponse,
  RecognizeNailTexturesOptions,
} from "./types.ts";
