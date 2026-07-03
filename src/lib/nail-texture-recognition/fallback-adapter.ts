import {
  detectNailRegionsFromImageData,
  type ImagePixels,
} from "../nail-image-detection.ts";
import type {
  NailTextureCandidate,
  NailTextureRecognitionResult,
  RecognizeNailTexturesOptions,
} from "./types.ts";
import { inferSuggestedFingers } from "./finger-assignment.ts";

function toCandidateId(index: number): string {
  return `fallback-${index + 1}`;
}

export function recognizeNailTexturesWithFallback(
  source: ImagePixels,
  options: Pick<RecognizeNailTexturesOptions, "maxCandidates"> = {}
): NailTextureRecognitionResult {
  const startedAt = performance.now();
  const maxCandidates = Math.max(1, options.maxCandidates ?? 10);
  const regions = detectNailRegionsFromImageData(source)
    .slice(0, maxCandidates)
    .sort((a, b) => a.cx - b.cx);
  const inferredFingers = inferSuggestedFingers(regions.length);

  const candidates: NailTextureCandidate[] = regions.map((region, index) => ({
    id: toCandidateId(index),
    cx: region.cx,
    cy: region.cy,
    length: region.length,
    width: region.width,
    angle: region.angle,
    score: region.score,
    confidence: region.confidence,
    source: "saliency",
    suggestedFinger: inferredFingers[index] ?? null,
  }));

  return {
    candidates,
    backend: "fallback",
    elapsedMs: performance.now() - startedAt,
    warnings: candidates.length ? [] : ["no_candidates_detected"],
  };
}
