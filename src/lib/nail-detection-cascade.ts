/**
 * 美甲识别级联共享库：模型/规则识别 → 手部几何兜底 → 局部近景兜底的编排逻辑。
 *
 * 自 `NailArtPicker` 组件原样抽出（逻辑逐行保持，仅调整导入路径并导出类型），
 * 供 `/ar-tryon` 选择器与编辑器共用；识别行为、警告过滤与降级顺序均不变。
 */
import {
  recognizeNailTexturesInWorker,
  type NailMask,
  type NailTextureCandidateConfidence,
  type NailTextureCandidateSource,
} from "@/lib/nail-texture-recognition";
import { remapNailTextureCandidatesToOriginal } from "@/lib/nail-texture-recognition/input-scaling";
import { detectNailsFromHandImage } from "@/lib/nail-hand-geometry-detection";
import {
  detectPartialCloseupNails,
  type PartialCloseupDetectionDiagnostics,
} from "@/lib/nail-partial-closeup-detection";

/** 识别输入的最长边上限：原图等比缩放到该尺寸后再送入识别 worker。 */
export const MAX_DETECTION_DIM = 800;
/** 识别 worker 的超时时间（毫秒）。 */
export const NAIL_RECOGNITION_WORKER_TIMEOUT_MS = 15_000;
/** 纹理识别模型 manifest 地址（公开环境变量，未配置时为 undefined）。 */
export const NAIL_TEXTURE_MODEL_MANIFEST_URL =
  process.env.NEXT_PUBLIC_NAIL_TEXTURE_MODEL_MANIFEST_URL?.trim() || undefined;

/** 识别级联返回的单个甲面区域（原图坐标域）；组件内的编辑态类型在其上扩展。 */
export interface NailDetectionRegion {
  id: string;
  cx: number;
  cy: number;
  angle: number;
  nl: number;
  nw: number;
  assignedFinger: number | null;
  confidence?: NailTextureCandidateConfidence;
  source?: NailTextureCandidateSource;
  mask?: NailMask;
  warnings?: string[];
}

/** 一次识别级联的汇总信息（后端、耗时、模型版本、警告等）。 */
export interface DetectionSummary {
  backend: "model" | "fallback";
  assistedByHandGeometry?: boolean;
  assistedByPartialCloseup?: boolean;
  modelVersion?: string;
  modelBackend?: "webgpu" | "wasm" | "fallback";
  elapsedMs: number;
  workerElapsedMs?: number;
  maxCandidates: number;
  workerTimeoutMs: number;
  partialCloseupDiagnostics?: PartialCloseupDetectionDiagnostics;
  warnings: string[];
}

/** 局部近景辅助定位生效时应在界面上隐藏的基础设施类警告码。 */
export const PARTIAL_CLOSEUP_HIDDEN_WARNING_CODES = new Set([
  "worker_unavailable_used_main_thread",
  "worker_timeout_used_main_thread",
  "model_runtime_unavailable_on_server",
  "no_supported_model_backend",
  "onnx_runtime_not_loaded",
  "onnx_session_init_failed",
  "onnx_session_or_tensor_unavailable",
  "model_outputs_empty_used_fallback",
  "model_unavailable_used_partial_closeup",
  "mediapipe_no_hand_detected",
  "mediapipe_no_nail_geometry",
  "mediapipe_hand_detection_failed",
]);

export function isPartialCloseupInfrastructureWarning(warning: string): boolean {
  if (PARTIAL_CLOSEUP_HIDDEN_WARNING_CODES.has(warning)) return true;
  return ["model_manifest_error", "model_inference_error", "onnx_session_init_failed"].some(
    (prefix) => warning.startsWith(prefix)
  );
}

/**
 * 从整图 mask 栅格推导候选帧几何（原图坐标域）。
 *
 * 口径与 v1.2.169 detect 候选几何一致：mask 为覆盖整图的栅格（`originX/originY` 恒 0、
 * `scale` 同 postprocess 口径，几何推导只消费 `width/height/data`），取二值实心
 * （data=1）外接框后按 `imageWidth/mask.width`、`imageHeight/mask.height` 逐轴映射回
 * 原图；实心边界算法与 `vlm-refinement.ts` 的 `solidBoundsFromGrid` 相同。
 * 无前景像素返回 null。
 */
export function frameGeometryFromMask(
  mask: NailMask,
  imageWidth: number,
  imageHeight: number
): { cx: number; cy: number; length: number; width: number } | null {
  let minX = mask.width;
  let minY = mask.height;
  let maxX = -1;
  let maxY = -1;
  for (let y = 0; y < mask.height; y += 1) {
    const rowOffset = y * mask.width;
    for (let x = 0; x < mask.width; x += 1) {
      if (!mask.data[rowOffset + x]) continue;
      if (x < minX) minX = x;
      if (x > maxX) maxX = x;
      if (y < minY) minY = y;
      if (y > maxY) maxY = y;
    }
  }
  if (maxX < 0) return null;
  const scaleX = imageWidth / mask.width;
  const scaleY = imageHeight / mask.height;
  return {
    cx: ((minX + maxX + 1) / 2) * scaleX,
    cy: ((minY + maxY + 1) / 2) * scaleY,
    length: (maxY - minY + 1) * scaleY,
    width: (maxX - minX + 1) * scaleX,
  };
}

export async function computeImageDetectedNailRegions(
  image: HTMLImageElement,
  imageData: ImageData,
  originalWidth: number,
  originalHeight: number,
  signal?: AbortSignal
): Promise<{
  regions: NailDetectionRegion[];
  originalRegions: NailDetectionRegion[];
  summary: DetectionSummary;
}> {
  const result = await recognizeNailTexturesInWorker(imageData, {
    preferModel: true,
    manifestUrl: NAIL_TEXTURE_MODEL_MANIFEST_URL,
    maxCandidates: 10,
    workerTimeoutMs: NAIL_RECOGNITION_WORKER_TIMEOUT_MS,
    signal,
  });

  const candidates = remapNailTextureCandidatesToOriginal(
    result.candidates,
    {
      scaleX: imageData.width / originalWidth,
      scaleY: imageData.height / originalHeight,
    },
    originalWidth,
    originalHeight
  );

  const modelOrRuleRegions = candidates.map((candidate) => ({
      id: candidate.id,
      cx: candidate.cx,
      cy: candidate.cy,
      angle: candidate.angle,
      nl: candidate.length,
      nw: candidate.width,
      assignedFinger: candidate.suggestedFinger,
      confidence: candidate.confidence,
      source: candidate.source,
      mask: candidate.mask,
      warnings: [...(candidate.warnings ?? [])],
  }));
  const fallbackUsed = result.backend === "fallback";
  const detectionWarnings = [...result.warnings];
  let handGeometryRegions: NailDetectionRegion[] = [];
  let partialCloseupRegions: NailDetectionRegion[] = [];
  let partialCloseupDiagnostics: PartialCloseupDetectionDiagnostics | undefined;
  if (fallbackUsed) {
    try {
      const handDetection = await detectNailsFromHandImage(image, { signal });
      detectionWarnings.push(...handDetection.warnings);
      handGeometryRegions = handDetection.candidates.map((candidate) => ({
        id: candidate.id,
        cx: candidate.cx,
        cy: candidate.cy,
        angle: candidate.angle,
        nl: candidate.length,
        nw: candidate.width,
        assignedFinger: candidate.suggestedFinger,
        confidence: candidate.confidence,
        source: candidate.source,
        warnings: [...(candidate.warnings ?? [])],
      }));
    } catch (reason) {
      const error = reason instanceof Error ? reason : new Error(String(reason));
      if (error.name === "AbortError") throw error;
      detectionWarnings.push("mediapipe_hand_detection_failed");
    }
  }
  if (fallbackUsed && handGeometryRegions.length === 0) {
    const partialDetection = detectPartialCloseupNails(imageData);
    partialCloseupDiagnostics = partialDetection.diagnostics;
    const partialCandidates = remapNailTextureCandidatesToOriginal(
      partialDetection.candidates,
      {
        scaleX: imageData.width / originalWidth,
        scaleY: imageData.height / originalHeight,
      },
      originalWidth,
      originalHeight
    );
    partialCloseupRegions = partialCandidates.map((candidate) => ({
      id: candidate.id,
      cx: candidate.cx,
      cy: candidate.cy,
      angle: candidate.angle,
      nl: candidate.length,
      nw: candidate.width,
      assignedFinger: candidate.suggestedFinger,
      confidence: candidate.confidence,
      source: candidate.source,
      warnings: [...(candidate.warnings ?? [])],
    }));
    if (partialCloseupRegions.length > 0) {
      const obsoleteWarnings = new Set([
        "mediapipe_no_hand_detected",
        "mediapipe_no_nail_geometry",
      ]);
      for (let index = detectionWarnings.length - 1; index >= 0; index -= 1) {
        if (obsoleteWarnings.has(detectionWarnings[index])) detectionWarnings.splice(index, 1);
      }
      detectionWarnings.push("model_unavailable_used_partial_closeup");
    } else {
      detectionWarnings.push("fallback_candidates_hidden_manual_selection_required");
    }
  }

  const assistedRegions =
    handGeometryRegions.length > 0 ? handGeometryRegions : partialCloseupRegions;
  const regions = fallbackUsed ? assistedRegions : modelOrRuleRegions;
  const originalRegions = fallbackUsed
    ? [...modelOrRuleRegions, ...assistedRegions]
    : modelOrRuleRegions;

  return {
    regions,
    originalRegions,
    summary: {
      backend: result.backend,
      assistedByHandGeometry: fallbackUsed && handGeometryRegions.length > 0,
      assistedByPartialCloseup: fallbackUsed && partialCloseupRegions.length > 0,
      modelVersion: result.modelVersion,
      modelBackend: result.modelInfo?.backend,
      elapsedMs: result.elapsedMs,
      workerElapsedMs: result.workerElapsedMs,
      maxCandidates: 10,
      workerTimeoutMs: NAIL_RECOGNITION_WORKER_TIMEOUT_MS,
      partialCloseupDiagnostics,
      warnings: detectionWarnings,
    },
  };
}
