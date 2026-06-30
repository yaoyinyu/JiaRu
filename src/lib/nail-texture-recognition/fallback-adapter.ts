import {
  detectNailRegionsFromImageData,
  type ImagePixels,
} from "../nail-image-detection.ts";
import type {
  NailTextureCandidate,
  NailTextureRecognitionResult,
} from "./types.ts";

function inferSuggestedFingers(candidateCount: number): number[] {
  if (candidateCount === 4) return [1, 2, 3, 4];
  if (candidateCount >= 5) return [0, 1, 2, 3, 4];
  return [1, 2, 3, 4, 0];
}

function toCandidateId(index: number): string {
  return `fallback-${index + 1}`;
}

export function recognizeNailTexturesWithFallback(
  source: ImagePixels
): NailTextureRecognitionResult {
  const startedAt = performance.now();
  const regions = detectNailRegionsFromImageData(source)
    .slice(0, 5)
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
