import type {
  NailDebugSampleCandidate,
  NailDebugSampleRecord,
} from "./nail-texture-debug-sample.ts";

export type DebugSamplePriorityTier = "high" | "medium" | "low";

export interface DebugSamplePriorityReason {
  code:
    | "fallback_backend_used"
    | "model_runtime_warning"
    | "low_confidence_corrected"
    | "high_confidence_deleted"
    | "manual_candidate_added"
    | "large_geometry_adjustment"
    | "finger_reassignment"
    | "extraction_quality_issue"
    | "highlight_or_contamination_warning";
  weight: number;
  message: string;
}

export interface DebugSamplePrioritySummary {
  addedCandidates: number;
  manualAddedCandidates: number;
  removedCandidates: number;
  matchedCandidates: number;
  lowConfidenceCorrections: number;
  highConfidenceDeletions: number;
  largeAdjustments: number;
  fingerReassignments: number;
  extractionIssueCandidates: number;
  warningCandidates: number;
}

export interface DebugSamplePriorityAssessment {
  imageId: string;
  backend: NailDebugSampleRecord["backend"];
  modelVersion: string;
  modelBackend?: NailDebugSampleRecord["modelBackend"];
  elapsedMs: number;
  priorityScore: number;
  priorityTier: DebugSamplePriorityTier;
  reasons: DebugSamplePriorityReason[];
  summary: DebugSamplePrioritySummary;
}

interface CandidatePair {
  original: NailDebugSampleCandidate;
  corrected: NailDebugSampleCandidate;
}

const MODEL_RUNTIME_WARNING_PREFIXES = [
  "model_manifest_error",
  "model_inference_error",
  "onnx_runtime_not_loaded",
  "onnx_session_init_failed",
  "onnx_session_or_tensor_unavailable",
  "model_outputs_empty_used_fallback",
  "model_runtime_unavailable_on_server",
  "worker_unavailable_used_main_thread",
];

const EXTRACTION_WARNING_CODES = new Set([
  "dirty_mask_crop",
  "mask_crop_touches_edge",
  "mask_foreground_too_small",
]);

const HIGHLIGHT_WARNING_CODES = new Set([
  "highlight_hotspots",
  "dirty_mask_crop",
]);

function hasModelRuntimeWarning(warnings: string[]): boolean {
  return warnings.some((warning) =>
    MODEL_RUNTIME_WARNING_PREFIXES.some((prefix) => warning.startsWith(prefix))
  );
}

function buildPairs(record: NailDebugSampleRecord): {
  pairs: CandidatePair[];
  added: NailDebugSampleCandidate[];
  removed: NailDebugSampleCandidate[];
} {
  const originalById = new Map(record.originalCandidates.map((candidate) => [candidate.id, candidate]));
  const correctedById = new Map(record.correctedCandidates.map((candidate) => [candidate.id, candidate]));

  const pairs: CandidatePair[] = [];
  for (const corrected of record.correctedCandidates) {
    const original = originalById.get(corrected.id);
    if (original) pairs.push({ original, corrected });
  }

  const added = record.correctedCandidates.filter((candidate) => !originalById.has(candidate.id));
  const removed = record.originalCandidates.filter((candidate) => !correctedById.has(candidate.id));

  return { pairs, added, removed };
}

function computeCenterShiftRatio(
  imageWidth: number,
  imageHeight: number,
  original: NailDebugSampleCandidate,
  corrected: NailDebugSampleCandidate
): number {
  const dx = corrected.cx - original.cx;
  const dy = corrected.cy - original.cy;
  const diagonal = Math.hypot(imageWidth, imageHeight) || 1;
  return Math.hypot(dx, dy) / diagonal;
}

function computeScaleDeltaRatio(
  original: NailDebugSampleCandidate,
  corrected: NailDebugSampleCandidate
): number {
  const originalArea = Math.max(1, original.length * original.width);
  const correctedArea = Math.max(1, corrected.length * corrected.width);
  return Math.abs(correctedArea - originalArea) / originalArea;
}

function candidateHasExtractionIssue(candidate: NailDebugSampleCandidate): boolean {
  return Boolean(
    candidate.extractionDiagnostics &&
      (!candidate.extractionDiagnostics.qualityOk ||
        candidate.extractionDiagnostics.qualityWarnings.some((warning) =>
          EXTRACTION_WARNING_CODES.has(warning)
        ))
  );
}

function candidateHasHighlightOrContaminationWarning(candidate: NailDebugSampleCandidate): boolean {
  const warningSet = new Set([
    ...candidate.warnings,
    ...(candidate.extractionDiagnostics?.qualityWarnings ?? []),
  ]);
  if ([...warningSet].some((warning) => HIGHLIGHT_WARNING_CODES.has(warning))) {
    return true;
  }
  return (candidate.extractionDiagnostics?.highlightRatio ?? 0) >= 0.12;
}

function tierFromScore(score: number): DebugSamplePriorityTier {
  if (score >= 7) return "high";
  if (score >= 3) return "medium";
  return "low";
}

export function assessDebugSamplePriority(
  record: NailDebugSampleRecord
): DebugSamplePriorityAssessment {
  const reasons: DebugSamplePriorityReason[] = [];
  const { pairs, added, removed } = buildPairs(record);

  const lowConfidenceCorrections = pairs.filter(
    (pair) => pair.original.confidence === "low" && pair.corrected.confidence !== "low"
  );
  if (lowConfidenceCorrections.length > 0) {
    reasons.push({
      code: "low_confidence_corrected",
      weight: 3,
      message: `${lowConfidenceCorrections.length} low-confidence model candidates were corrected into usable regions`,
    });
  }

  const highConfidenceDeletions = removed.filter((candidate) => candidate.confidence === "high");
  if (highConfidenceDeletions.length > 0) {
    reasons.push({
      code: "high_confidence_deleted",
      weight: 4,
      message: `${highConfidenceDeletions.length} high-confidence original candidates were deleted by the user`,
    });
  }

  const manualAddedCandidates = added.filter((candidate) => candidate.source === "manual");
  if (manualAddedCandidates.length > 0) {
    reasons.push({
      code: "manual_candidate_added",
      weight: 3,
      message: `${manualAddedCandidates.length} candidate regions were added manually, which suggests detector coverage gaps`,
    });
  }

  const largeAdjustments = pairs.filter((pair) => {
    const shiftRatio = computeCenterShiftRatio(record.image.width, record.image.height, pair.original, pair.corrected);
    const scaleDeltaRatio = computeScaleDeltaRatio(pair.original, pair.corrected);
    return shiftRatio >= 0.08 || scaleDeltaRatio >= 0.25;
  });
  if (largeAdjustments.length > 0) {
    reasons.push({
      code: "large_geometry_adjustment",
      weight: 2,
      message: `${largeAdjustments.length} matched candidates needed large move/scale corrections`,
    });
  }

  const fingerReassignments = pairs.filter(
    (pair) => pair.original.assignedFinger !== pair.corrected.assignedFinger
  );
  if (fingerReassignments.length > 0) {
    reasons.push({
      code: "finger_reassignment",
      weight: 1,
      message: `${fingerReassignments.length} candidates were reassigned to different fingers`,
    });
  }

  if (record.backend === "fallback") {
    reasons.push({
      code: "fallback_backend_used",
      weight: 2,
      message: "fallback backend handled this sample, so it is useful for model-vs-fallback gap analysis",
    });
  }

  if (hasModelRuntimeWarning(record.warnings)) {
    reasons.push({
      code: "model_runtime_warning",
      weight: 2,
      message: "sample contains runtime/model warnings and should be reviewed for model availability failures",
    });
  }

  const extractionIssueCandidates = record.correctedCandidates.filter(candidateHasExtractionIssue);
  if (extractionIssueCandidates.length > 0) {
    reasons.push({
      code: "extraction_quality_issue",
      weight: 2,
      message: `${extractionIssueCandidates.length} corrected candidates still report extraction quality issues`,
    });
  }

  const warningCandidates = record.correctedCandidates.filter(candidateHasHighlightOrContaminationWarning);
  if (warningCandidates.length > 0) {
    reasons.push({
      code: "highlight_or_contamination_warning",
      weight: 2,
      message: `${warningCandidates.length} corrected candidates still show glare/contamination warning signals`,
    });
  }

  const priorityScore = reasons.reduce((sum, reason) => sum + reason.weight, 0);

  return {
    imageId: record.imageId,
    backend: record.backend,
    modelVersion: record.modelVersion,
    modelBackend: record.modelBackend,
    elapsedMs: record.elapsedMs,
    priorityScore,
    priorityTier: tierFromScore(priorityScore),
    reasons,
    summary: {
      addedCandidates: added.length,
      manualAddedCandidates: manualAddedCandidates.length,
      removedCandidates: removed.length,
      matchedCandidates: pairs.length,
      lowConfidenceCorrections: lowConfidenceCorrections.length,
      highConfidenceDeletions: highConfidenceDeletions.length,
      largeAdjustments: largeAdjustments.length,
      fingerReassignments: fingerReassignments.length,
      extractionIssueCandidates: extractionIssueCandidates.length,
      warningCandidates: warningCandidates.length,
    },
  };
}
