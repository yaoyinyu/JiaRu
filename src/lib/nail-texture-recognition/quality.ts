import type { NailTextureCandidate } from "./types.ts";

export interface RankNailTextureCandidatesOptions {
  imageWidth: number;
  imageHeight: number;
  maxCandidates?: number;
}

function adjustedConfidence(score: number): NailTextureCandidate["confidence"] {
  if (score >= 0.75) return "high";
  if (score >= 0.5) return "medium";
  return "low";
}

function areaRatio(candidate: NailTextureCandidate, imageArea: number): number {
  return (candidate.width * candidate.length) / imageArea;
}

function aspectRatio(candidate: NailTextureCandidate): number {
  const shorter = Math.min(candidate.width, candidate.length);
  const longer = Math.max(candidate.width, candidate.length);
  return shorter <= 0 ? Number.POSITIVE_INFINITY : longer / shorter;
}

function scorePenalty(candidate: NailTextureCandidate, imageArea: number): number {
  let penalty = 0;
  const ratio = areaRatio(candidate, imageArea);
  if (ratio < 0.0008 || ratio > 0.08) penalty += 0.4;
  const aspect = aspectRatio(candidate);
  if (aspect < 1 || aspect > 4.5) penalty += 0.2;
  return penalty;
}

export function rankNailTextureCandidates(
  candidates: NailTextureCandidate[],
  options: RankNailTextureCandidatesOptions
): NailTextureCandidate[] {
  const imageArea = options.imageWidth * options.imageHeight;
  const maxCandidates = options.maxCandidates ?? 5;

  return candidates
    .map((candidate) => {
      const adjustedScore = Math.max(0, candidate.score - scorePenalty(candidate, imageArea));
      return {
        ...candidate,
        score: adjustedScore,
        confidence: adjustedConfidence(adjustedScore),
      };
    })
    .filter((candidate) => {
      const ratio = areaRatio(candidate, imageArea);
      return ratio >= 0.0008 && ratio <= 0.08;
    })
    .filter((candidate) => candidate.score >= 0.35)
    .sort((a, b) => b.score - a.score)
    .slice(0, maxCandidates)
    .sort((a, b) => a.cx - b.cx);
}
